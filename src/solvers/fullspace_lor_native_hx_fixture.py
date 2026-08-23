"""Small real p-refined positive LOR/HX fixture for the V7 L2 lane.

The fixture is deliberately separate from the L2 runner.  It builds a real
structured high-order mesh and its GLL-refined p1 auxiliary mesh, keeps the
full PETSc row layout (including periodic slave rows), and assembles only the
positive auxiliary sparse operators.  The high-order operator remains the
matrix-free :class:`FullspaceMpcFormAction` path.

This is a focused oracle, not a formal N2 implementation: it does not build a
physical DtN action, a high-order AIJ matrix, or a global transfer matrix.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI
from petsc4py import PETSc

from ..common.config_3d import target_stage4_config
from ..constraints.floquet_3d import build_double_floquet_mpc
from ..geometry.mesh_builder_3d import (
    _mark_boundary_facets,
    _mark_cells,
    _stage4_axis_plan,
    _structured_hexa_mesh,
)
from .fullspace_lor_topology import (
    _alltoallv,
    _entity_coordinates,
    _pack_canonical_edges,
    build_canonical_lor_subedge_topology,
    global_lor_edge_roundtrip,
)
from .fullspace_lor_transfer import (
    _edge_endpoints,
    _gll_nodes,
    build_local_lor_transfer,
    build_reference_factor_lor_transfer,
)
from .fullspace_mpc_action import build_fullspace_mpc_form_action


L2_SOURCE_NAMES = ("random", "gradient", "curl", "checkerboard")
L2_RHO_LIMITS = {
    "random": 0.45,
    "gradient": 0.25,
    "curl": 0.45,
    "checkerboard": 0.60,
}
L2_CG_RTOL = 1.0e-8
L2_CG_MAX_IT = 40
L2_REPEAT_LIMIT = 1.0e-13


def l2_source_formula(name: str) -> str:
    """Return the frozen source definition used by the L2 oracle."""

    formulas = {
        "random": (
            "analytic deterministic pseudo-random edge field from fixed "
            "noninteger trigonometric frequencies and phases"
        ),
        "gradient": "grad(sin(2*pi*sx)*sin(2*pi*sy)*sin(2*pi*sz))",
        "curl": "curl((0,0,sin(2*pi*sx)*sin(2*pi*sy)*sin(2*pi*sz)))",
        "checkerboard": (
            "R4 fixed 8-cycle field: "
            "(high_x*high_y*high_z, high_y*high_z, high_z*high_x)"
        ),
    }
    try:
        return formulas[name]
    except KeyError as exc:
        raise ValueError(f"unknown L2 source {name!r}") from exc


def _l2_unit_coordinates(coordinates: np.ndarray, cfg: Any) -> tuple[np.ndarray, ...]:
    x, y, z = np.asarray(coordinates, dtype=np.float64)
    sx = (x - float(cfg.x_min)) / (float(cfg.x_max) - float(cfg.x_min))
    sy = (y - float(cfg.y_min)) / (float(cfg.y_max) - float(cfg.y_min))
    sz = (z - float(cfg.domain_z_min)) / (
        float(cfg.domain_z_max) - float(cfg.domain_z_min)
    )
    return sx, sy, sz


def _l2_analytic_values(name: str, coordinates: np.ndarray, cfg: Any) -> np.ndarray:
    sx, sy, sz = _l2_unit_coordinates(coordinates, cfg)
    pi = np.pi
    ax = 2.0 * pi / (float(cfg.x_max) - float(cfg.x_min))
    ay = 2.0 * pi / (float(cfg.y_max) - float(cfg.y_min))
    az = 2.0 * pi / (float(cfg.domain_z_max) - float(cfg.domain_z_min))
    sin_x = np.sin(2.0 * pi * sx)
    sin_y = np.sin(2.0 * pi * sy)
    sin_z = np.sin(2.0 * pi * sz)
    cos_x = np.cos(2.0 * pi * sx)
    cos_y = np.cos(2.0 * pi * sy)
    cos_z = np.cos(2.0 * pi * sz)
    if name == "random":
        return np.vstack(
            (
                np.sin(2.0 * pi * (1.37 * sx + 0.23))
                * np.cos(2.0 * pi * (0.73 * sy + 0.11))
                * np.sin(2.0 * pi * (1.19 * sz + 0.37)),
                np.cos(2.0 * pi * (0.91 * sx + 0.07))
                * np.sin(2.0 * pi * (1.41 * sy + 0.29))
                * np.cos(2.0 * pi * (0.67 * sz + 0.19)),
                np.sin(2.0 * pi * (1.23 * sx + 0.31))
                * np.sin(2.0 * pi * (0.83 * sy + 0.17))
                * np.cos(2.0 * pi * (1.07 * sz + 0.41)),
            )
        ).astype(np.complex128)
    if name == "gradient":
        return np.vstack(
            (
                ax * cos_x * sin_y * sin_z,
                ay * sin_x * cos_y * sin_z,
                az * sin_x * sin_y * cos_z,
            )
        ).astype(np.complex128)
    if name == "curl":
        return np.vstack(
            (
                ay * sin_x * cos_y * sin_z,
                -ax * cos_x * sin_y * sin_z,
                np.zeros_like(sin_x),
            )
        ).astype(np.complex128)
    if name == "checkerboard":
        high_x = np.sin(8.0 * ax * (coordinates[0] - float(cfg.x_min)))
        high_y = np.sin(8.0 * ay * (coordinates[1] - float(cfg.y_min)))
        high_z = np.sin(8.0 * az * (coordinates[2] - float(cfg.domain_z_min)))
        return np.vstack(
            (high_x * high_y * high_z, high_y * high_z, high_z * high_x)
        ).astype(np.complex128)
    raise ValueError(f"unknown analytic L2 source {name!r}")


def _refined_axis(values: np.ndarray, degree: int) -> np.ndarray:
    nodes = _gll_nodes(degree)
    pieces: list[float] = []
    for left, right in zip(values[:-1], values[1:], strict=True):
        pieces.extend(float(left + (right - left) * node) for node in nodes[:-1])
    pieces.append(float(values[-1]))
    result = np.asarray(pieces, dtype=default_real_type)
    if result.size < 2 or not np.all(np.diff(result) > 0.0):
        raise RuntimeError("GLL-refined coordinate axis is not strictly ordered")
    return result


class _P1IdentityTransfer:
    """Topology-only identity for a lowest-order p1 refined edge cell."""

    degree = 1
    edge_count = 12
    nodes = np.asarray([0.0, 1.0], dtype=np.float64)

    @staticmethod
    def high_to_lor_many(values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=np.complex128)
        if values.ndim != 2 or values.shape[1] != 12 or not 1 <= values.shape[0] <= 32:
            raise ValueError("p1 topology batch has an unexpected shape")
        return values.copy()

    @staticmethod
    def lor_to_high_many(values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=np.complex128)
        if values.ndim != 2 or values.shape[1] != 12 or not 1 <= values.shape[0] <= 32:
            raise ValueError("p1 topology batch has an unexpected shape")
        return values.copy()


def _coordinate_key(coordinate: np.ndarray) -> tuple[int, int, int]:
    return tuple(int(round(float(value) * 1.0e10)) for value in coordinate)


def _scalar_periodic_mpc(space: Any, cfg: Any) -> tuple[Any, dict[str, Any]]:
    """Build scalar x/y Floquet constraints with a bounded owner lookup.

    Only boundary target keys are exchanged.  Owned coordinate inventories and
    full finite-element row tables are never replicated; ``MultiPointConstraint``
    owns the finalized remote-master representation.
    """

    import dolfinx_mpc

    comm = space.mesh.comm
    index_map = space.dofmap.index_map
    local_count = int(index_map.size_local)
    storage_count = local_count + int(index_map.num_ghosts)
    local_ids = np.arange(storage_count, dtype=np.int32)
    global_ids = np.asarray(index_map.local_to_global(local_ids), dtype=np.int64)
    coordinates = np.asarray(space.tabulate_dof_coordinates(), dtype=np.float64)
    if coordinates.shape[0] != storage_count:
        raise RuntimeError("scalar coordinate storage does not match index map")

    owned_by_key = {
        _coordinate_key(coordinates[local]): (int(global_ids[local]), int(comm.rank))
        for local in range(local_count)
    }

    tolerance = 1.0e-10
    slave_local: list[int] = []
    master_global: list[int] = []
    master_owner: list[int] = []
    coefficients: list[complex] = []
    target_keys: dict[int, tuple[int, int, int]] = {}
    xmin, xmax = float(cfg.x_min), float(cfg.x_max)
    ymin, ymax = float(cfg.y_min), float(cfg.y_max)
    for local in range(local_count):
        coordinate = coordinates[local]
        x_upper = abs(float(coordinate[0]) - xmax) <= tolerance
        y_upper = abs(float(coordinate[1]) - ymax) <= tolerance
        if not (x_upper or y_upper):
            continue
        target = coordinate.copy()
        target[0] = xmin if x_upper else target[0]
        target[1] = ymin if y_upper else target[1]
        slave_local.append(local)
        target_keys[local] = _coordinate_key(target)
        coefficient = complex(cfg.floquet_phase_x) if x_upper else 1.0 + 0.0j
        if y_upper:
            coefficient *= complex(cfg.floquet_phase_y)
        coefficients.append(coefficient)

    requests = [[] for _ in range(comm.size)]
    for local, key in target_keys.items():
        for destination in range(comm.size):
            requests[destination].append(
                (int(comm.rank), int(local), int(key[0]), int(key[1]), int(key[2]))
            )
    incoming_requests = comm.alltoall(requests)
    replies = [[] for _ in range(comm.size)]
    for requester_records in incoming_requests:
        for requester, local, key_x, key_y, key_z in requester_records:
            target_entry = owned_by_key.get((key_x, key_y, key_z))
            if target_entry is not None:
                replies[int(requester)].append(
                    (int(local), int(target_entry[0]), int(target_entry[1]))
                )
    incoming_replies = comm.alltoall(replies)
    resolved: dict[int, tuple[int, int]] = {}
    for records in incoming_replies:
        for local, global_id, owner in records:
            previous = resolved.get(int(local))
            current = (int(global_id), int(owner))
            if previous is not None and previous != current:
                raise RuntimeError("scalar periodic owner replies disagree")
            resolved[int(local)] = current
    if set(resolved) != set(target_keys):
        raise RuntimeError("scalar periodic master owner route is incomplete")
    for local in slave_local:
        global_id, owner = resolved[int(local)]
        master_global.append(global_id)
        master_owner.append(owner)

    order = np.argsort(np.asarray(slave_local, dtype=np.int32), kind="stable")
    slave_local_array = np.asarray(slave_local, dtype=np.int32)[order]
    master_global_array = np.asarray(master_global, dtype=np.int64)[order]
    master_owner_array = np.asarray(master_owner, dtype=np.int32)[order]
    coefficient_array = np.asarray(coefficients, dtype=np.complex128)[order]
    offsets = np.arange(slave_local_array.size + 1, dtype=np.int32)
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.add_constraint(
        space,
        slave_local_array,
        master_global_array,
        coefficient_array,
        master_owner_array,
        offsets,
    )
    mpc.finalize()
    global_slave_count = int(comm.allreduce(slave_local_array.size, op=MPI.SUM))
    return mpc, {
        "local_slave_rows": int(slave_local_array.size),
        "global_slave_rows": global_slave_count,
        "phase_application": "finalized_floquet_mpc_once",
        "slave_master_complete": True,
        "metadata_allgather": False,
        "metadata_exchange": "boundary_key_broadcast_alltoall",
        "x_upper_rows": int(sum(abs(float(coordinates[row, 0]) - xmax) <= tolerance for row in slave_local)),
        "y_upper_rows": int(sum(abs(float(coordinates[row, 1]) - ymax) <= tolerance for row in slave_local)),
        "corner_rows": int(sum(
            abs(float(coordinates[row, 0]) - xmax) <= tolerance
            and abs(float(coordinates[row, 1]) - ymax) <= tolerance
            for row in slave_local
        )),
        "numeric_allgather": False,
    }


def _assemble_sparse(form: Any, *, mpc: Any | None = None) -> PETSc.Mat:
    compiled = fem.form(form)
    if mpc is None:
        matrix = fem_petsc.assemble_matrix(compiled, bcs=[])
    else:
        import dolfinx_mpc

        matrix = dolfinx_mpc.assemble_matrix(compiled, mpc, bcs=[])
    matrix.assemble()
    return matrix


def _piecewise_positive_coefficients(
    mesh_object: Any, cell_tags: Any, cfg: Any
) -> tuple[Any, Any, dict[str, Any]]:
    """Create DG0 positive curl and mass coefficients from physical tags."""

    coefficient_space = fem.functionspace(
        mesh_object,
        element("DG", mesh_object.basix_cell(), 0, dtype=default_real_type),
    )
    local_cells = int(mesh_object.topology.index_map(mesh_object.topology.dim).size_local)
    tags = np.full(local_cells, int(cfg.tags.air), dtype=np.int32)
    tags[np.asarray(cell_tags.indices, dtype=np.int32)] = np.asarray(
        cell_tags.values, dtype=np.int32
    )
    mu_by_tag = {
        int(cfg.tags.air): abs(1.0 / complex(cfg.mu_r)),
        int(cfg.tags.substrate): abs(1.0 / complex(cfg.mu_r)),
        int(cfg.tags.grating): abs(1.0 / complex(cfg.mu_r)),
    }
    eps_by_tag = {
        int(cfg.tags.air): abs(complex(cfg.eps_air)),
        int(cfg.tags.substrate): abs(complex(cfg.eps_substrate)),
        int(cfg.tags.grating): abs(complex(cfg.eps_grating)),
    }
    mu_values = np.asarray([mu_by_tag[int(tag)] for tag in tags], dtype=np.float64)
    mass_values = np.asarray(
        [cfg.k0**2 * eps_by_tag[int(tag)] for tag in tags], dtype=np.float64
    )
    mu_function = fem.Function(coefficient_space)
    mass_function = fem.Function(coefficient_space)
    mu_function.x.array[:local_cells] = mu_values
    mass_function.x.array[:local_cells] = mass_values
    mu_function.x.scatter_forward()
    mass_function.x.scatter_forward()
    local_counts = {
        name: int(np.count_nonzero(tags == int(tag)))
        for name, tag in (
            ("air", cfg.tags.air),
            ("substrate", cfg.tags.substrate),
            ("grating", cfg.tags.grating),
        )
    }
    local_count_array = np.asarray(
        [local_counts["air"], local_counts["substrate"], local_counts["grating"]],
        dtype=np.int64,
    )
    global_count_array = np.asarray(
        mesh_object.comm.allreduce(local_count_array, op=MPI.SUM), dtype=np.int64
    )
    counts = {
        name: int(global_count_array[index])
        for index, name in enumerate(("air", "substrate", "grating"))
    }
    audit = {
        "cell_counts": counts,
        "local_cell_counts": local_counts,
        "positive_coefficients": {
            name: {
                "mu_inverse": float(mu_by_tag[int(tag)]),
                "k0_squared_abs_epsilon": float(cfg.k0**2 * eps_by_tag[int(tag)]),
            }
            for name, tag in (
                ("air", cfg.tags.air),
                ("substrate", cfg.tags.substrate),
                ("grating", cfg.tags.grating),
            )
        },
        "local_cell_count": local_cells,
    }
    return mu_function, mass_function, audit


def _hermitian_transpose(matrix: PETSc.Mat) -> PETSc.Mat:
    result = PETSc.Mat()
    matrix.hermitianTranspose(result)
    return result


def _edge_records(
    edge_space: Any, node_space: Any
) -> tuple[dict[int, tuple[int, int, float, int]], int]:
    """Build raw edge metadata for this rank's owned rows only."""

    tdim = edge_space.mesh.topology.dim
    edge_map = edge_space.dofmap.index_map
    node_map = node_space.dofmap.index_map
    node_coordinates = np.asarray(node_space.tabulate_dof_coordinates(), dtype=np.float64)
    edge_storage = int(edge_map.size_local + edge_map.num_ghosts)
    node_storage = int(node_map.size_local + node_map.num_ghosts)
    edge_global = np.asarray(
        edge_map.local_to_global(np.arange(edge_storage, dtype=np.int32)), dtype=np.int64
    )
    node_global = np.asarray(
        node_map.local_to_global(np.arange(node_storage, dtype=np.int32)), dtype=np.int64
    )
    topology = edge_space.mesh.topology
    topology.create_connectivity(tdim, 1)
    topology.create_connectivity(1, 0)
    cell_to_edges = topology.connectivity(tdim, 1)
    edge_to_vertices = topology.connectivity(1, 0)
    cell_to_vertices = topology.connectivity(tdim, 0)
    edge_entity_dofs = edge_space.element.basix_element.entity_dofs[1]
    node_entity_dofs = node_space.element.basix_element.entity_dofs[0]
    local_cells = int(edge_space.mesh.topology.index_map(tdim).size_local)
    records: dict[int, tuple[int, int, float, int]] = {}
    tolerance = 1.0e-9
    for cell in range(local_cells):
        edge_local = np.asarray(edge_space.dofmap.cell_dofs(cell), dtype=np.int32)
        node_local = np.asarray(node_space.dofmap.cell_dofs(cell), dtype=np.int32)
        cell_node_coordinates = node_coordinates[node_local]
        cell_node_global = node_global[node_local]
        cell_vertices = np.asarray(cell_to_vertices.links(cell), dtype=np.int32)
        vertex_to_node_local = {
            int(vertex): int(node_local[int(node_entity_dofs[index][0])])
            for index, vertex in enumerate(cell_vertices)
        }
        cell_edges = np.asarray(cell_to_edges.links(cell), dtype=np.int32)
        for entity_index, edge_entity in enumerate(cell_edges):
            vertices = np.asarray(edge_to_vertices.links(int(edge_entity)), dtype=np.int32)
            if vertices.size != 2:
                raise RuntimeError("p1 edge topology does not have two endpoints")
            left_local = vertex_to_node_local[int(vertices[0])]
            right_local = vertex_to_node_local[int(vertices[1])]
            left_coordinate = node_coordinates[left_local]
            right_coordinate = node_coordinates[right_local]
            delta = right_coordinate - left_coordinate
            axis = int(np.argmax(np.abs(delta)))
            if np.count_nonzero(np.abs(delta) > tolerance) != 1:
                raise RuntimeError("p1 edge topology is not axis aligned")
            low_local, high_local = (
                (left_local, right_local) if delta[axis] > 0.0 else (right_local, left_local)
            )
            edge_basis = int(edge_entity_dofs[entity_index][0])
            edge_gid = int(edge_global[int(edge_local[edge_basis])])
            low_gid = int(node_global[low_local])
            high_gid = int(node_global[high_local])
            length = float(np.linalg.norm(node_coordinates[high_local] - node_coordinates[low_local]))
            current = (int(low_gid), int(high_gid), float(length), int(axis))
            previous = records.get(edge_gid)
            if previous is not None and (
                previous[:2] != current[:2]
                or abs(previous[2] - current[2]) > tolerance
                or previous[3] != current[3]
            ):
                raise RuntimeError("raw p1 owned-edge metadata is inconsistent")
            records[edge_gid] = current
    owned_edge_ids = np.asarray(
        edge_map.local_to_global(
            np.arange(int(edge_map.size_local), dtype=np.int32)
        ),
        dtype=np.int64,
    )
    owned_set = set(int(value) for value in owned_edge_ids)
    owned_records = {
        edge_gid: record for edge_gid, record in records.items() if edge_gid in owned_set
    }
    if set(owned_records) != owned_set:
        raise RuntimeError("owned raw p1 edge metadata does not close this rank")
    metadata_bytes = int(
        sum(
            3 * np.dtype(np.int64).itemsize
            + np.dtype(np.float64).itemsize
            + np.dtype(np.int8).itemsize
            for _ in owned_records
        )
    )
    return owned_records, metadata_bytes


def _p1_transfer_local_indices(edge_space: Any, cell: int) -> np.ndarray:
    """Map canonical x/y/z p1 edge order to DOLFINx local edge rows."""

    topology = edge_space.mesh.topology
    tdim = topology.dim
    topology.create_connectivity(tdim, 1)
    topology.create_connectivity(1, 0)
    topology.create_connectivity(tdim, 0)
    cell_edges = np.asarray(topology.connectivity(tdim, 1).links(cell), dtype=np.int32)
    cell_vertices = np.asarray(topology.connectivity(tdim, 0).links(cell), dtype=np.int32)
    edge_to_vertices = topology.connectivity(1, 0)
    cell_coordinates = _entity_coordinates(edge_space, tdim, cell)
    lower = np.min(cell_coordinates, axis=0)
    upper = np.max(cell_coordinates, axis=0)
    starts, ends = _edge_endpoints(1)
    by_vertices: dict[frozenset[int], int] = {}
    for entity_index, edge_entity in enumerate(cell_edges):
        vertices = np.asarray(edge_to_vertices.links(int(edge_entity)), dtype=np.int32)
        by_vertices[frozenset(int(value) for value in vertices)] = entity_index
    entity_dofs = edge_space.element.basix_element.entity_dofs[1]
    local_indices = np.empty(12, dtype=np.int32)
    for edge_index, (start, end) in enumerate(zip(starts, ends, strict=True)):
        start_coordinate = lower + (upper - lower) * start
        end_coordinate = lower + (upper - lower) * end
        start_vertex = int(
            np.flatnonzero(
                np.max(np.abs(cell_coordinates - start_coordinate), axis=1) <= 1.0e-12
            )[0]
        )
        end_vertex = int(
            np.flatnonzero(
                np.max(np.abs(cell_coordinates - end_coordinate), axis=1) <= 1.0e-12
            )[0]
        )
        entity_index = by_vertices[
            frozenset((int(cell_vertices[start_vertex]), int(cell_vertices[end_vertex])))
        ]
        local_indices[edge_index] = int(entity_dofs[entity_index][0])
    if np.unique(local_indices).size != 12:
        raise RuntimeError("p1 transfer local edge permutation is not bijective")
    return local_indices


def _mpc_relation_table(space: Any, mpc: Any) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Return local owned/needed raw-to-master relations in global row ids."""

    index_map = space.dofmap.index_map
    master_index_map = mpc.function_space.dofmap.index_map
    local_count = int(index_map.size_local)
    storage_count = local_count + int(index_map.num_ghosts)
    global_ids = np.asarray(
        index_map.local_to_global(np.arange(storage_count, dtype=np.int32)),
        dtype=np.int64,
    )
    slaves = set(int(row) for row in np.asarray(mpc.slaves, dtype=np.int32))
    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    result: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for local_row in range(storage_count):
        global_row = int(global_ids[local_row])
        if local_row not in slaves or local_row >= offsets.size - 1:
            result[global_row] = (
                np.asarray([global_row], dtype=np.int64),
                np.asarray([1.0 + 0.0j], dtype=np.complex128),
            )
            continue
        start, stop = int(offsets[local_row]), int(offsets[local_row + 1])
        masters_local = np.asarray(mpc.masters.links(local_row), dtype=np.int32)
        row_coefficients = np.asarray(coefficients[start:stop], dtype=np.complex128)
        if masters_local.size != row_coefficients.size:
            raise RuntimeError("MPC relation has mismatched master coefficients")
        masters_global = np.asarray(
            master_index_map.local_to_global(masters_local), dtype=np.int64
        )
        if np.any(masters_global < 0) or np.any(
            masters_global >= int(index_map.size_global)
        ):
            raise RuntimeError("finalized MPC master global id exceeds full row layout")
        result[global_row] = (masters_global, row_coefficients)
    return result


def _constrained_rectangular_map(
    edge_layout: tuple[int, int],
    node_layout: tuple[int, int],
    expected_edge_range: tuple[int, int],
    expected_node_range: tuple[int, int],
    edge_records: dict[int, tuple[int, int, float, int]],
    edge_relations: dict[int, tuple[np.ndarray, np.ndarray]],
    node_relations: dict[int, tuple[np.ndarray, np.ndarray]],
    kind: str,
    comm: MPI.Comm,
) -> PETSc.Mat:
    """Build R_edge^H A_raw R_node without a rectangular identity extension."""

    matrix = PETSc.Mat().createAIJ(
        (
            tuple(int(value) for value in edge_layout),
            tuple(int(value) for value in node_layout),
        ),
        nnz=8,
        comm=comm,
    )
    matrix.setUp()
    left = matrix.createVecLeft()
    right = matrix.createVecRight()
    if left.getOwnershipRange() != tuple(int(value) for value in expected_edge_range):
        raise RuntimeError("rectangular map row ownership differs from edge space")
    if right.getOwnershipRange() != tuple(int(value) for value in expected_node_range):
        raise RuntimeError("rectangular map column ownership differs from node space")
    left.destroy()
    right.destroy()
    start, stop = matrix.getOwnershipRange()
    contributions: dict[tuple[int, int], complex] = {}
    for edge_gid in range(int(start), int(stop)):
        low_gid, high_gid, length, axis = edge_records[edge_gid]
        if length <= 0.0:
            raise RuntimeError("p1 edge has zero physical length")
        if kind == "gradient":
            raw_entries = ((int(low_gid), -1.0 + 0.0j), (int(high_gid), 1.0 + 0.0j))
        else:
            value = 0.5 * length if int(axis) == int(kind) else 0.0
            raw_entries = (
                (int(low_gid), complex(value)),
                (int(high_gid), complex(value)),
            )
        edge_masters, edge_coefficients = edge_relations[edge_gid]
        for raw_node_gid, raw_value in raw_entries:
            if raw_value == 0.0:
                continue
            node_masters, node_coefficients = node_relations[raw_node_gid]
            for edge_master, edge_coefficient in zip(
                edge_masters, edge_coefficients, strict=True
            ):
                for node_master, node_coefficient in zip(
                    node_masters, node_coefficients, strict=True
                ):
                    key = (int(edge_master), int(node_master))
                    contributions[key] = contributions.get(key, 0.0 + 0.0j) + (
                        np.conj(edge_coefficient) * raw_value * node_coefficient
                    )
    for (row, column), value in contributions.items():
        if value != 0.0:
            matrix.setValue(row, column, value, addv=PETSc.InsertMode.ADD_VALUES)
    matrix.assemble()
    return matrix


def _de_rham_maps(
    edge_space: Any,
    node_space: Any,
    edge_mpc: Any,
    node_mpc: Any,
    edge_matrix: PETSc.Mat,
    node_matrix: PETSc.Mat,
) -> tuple[PETSc.Mat, tuple[PETSc.Mat, ...], dict[str, Any], dict[int, tuple[int, int, float, int]]]:
    """Create constrained p1 incidence and edge-integral maps."""

    edge_records, metadata_bytes = _edge_records(edge_space, node_space)
    comm = edge_space.mesh.comm
    edge_map = edge_space.dofmap.index_map
    node_map = node_space.dofmap.index_map
    edge_layout = (int(edge_map.size_local), int(edge_map.size_global))
    node_layout = (int(node_map.size_local), int(node_map.size_global))
    edge_relations = _mpc_relation_table(edge_space, edge_mpc)
    node_relations = _mpc_relation_table(node_space, node_mpc)
    gradient = _constrained_rectangular_map(
        edge_layout,
        node_layout,
        edge_matrix.getOwnershipRange(),
        node_matrix.getOwnershipRange(),
        edge_records,
        edge_relations,
        node_relations,
        "gradient",
        comm,
    )
    vector_maps = tuple(
        _constrained_rectangular_map(
            edge_layout,
            node_layout,
            edge_matrix.getOwnershipRange(),
            node_matrix.getOwnershipRange(),
            edge_records,
            edge_relations,
            node_relations,
            str(axis),
            comm,
        )
        for axis in range(3)
    )
    audit = {
        "edge_record_count": len(edge_records),
        "metadata_entries": len(edge_records) + len(node_relations),
        "metadata_bytes": metadata_bytes,
        "metadata_scope": "owned_rows_and_needed_local_ghosts",
        "production_metadata_replacement_required": False,
        "gradient_kind": "R_edge_H_endpoint_incidence_R_node",
        "pi_kind": "R_edge_H_endpoint_average_times_physical_edge_length_R_node",
        "slave_rows_and_columns_zero": True,
        "rectangular_identity_extension": False,
        "max_edge_relation_master_global": int(
            max(
                (
                    int(np.max(masters))
                    for masters, _coefficients in edge_relations.values()
                    if masters.size
                ),
                default=-1,
            )
        ),
        "max_node_relation_master_global": int(
            max(
                (
                    int(np.max(masters))
                    for masters, _coefficients in node_relations.values()
                    if masters.size
                ),
                default=-1,
            )
        ),
        "edge_relation_global_rows": int(edge_map.size_global),
        "node_relation_global_rows": int(node_map.size_global),
    }
    gradient_adjoint = _hermitian_transpose(gradient)
    restrictions = tuple(_hermitian_transpose(matrix) for matrix in vector_maps)
    return gradient, (gradient_adjoint, *vector_maps), audit, edge_records


def _consistent_field(space: Any, floquet: Any) -> Any:
    field = fem.Function(floquet.mpc.function_space)
    field.interpolate(
        lambda coordinates: np.vstack(
            (
                coordinates[0] + 1j * (1.0 + coordinates[1]),
                2.0 * coordinates[1] + 1j * (2.0 + coordinates[2]),
                -coordinates[2] + 1j * (3.0 + coordinates[0]),
            )
        )
    )
    floquet.mpc.homogenize(field)
    floquet.mpc.backsubstitution(field)
    field.x.scatter_forward()
    return field


def _high_source(space: Any, floquet: Any) -> PETSc.Vec:
    field = _consistent_field(space, floquet)
    result = field.x.petsc_vec.copy()
    del field
    return result


class RealL2PositiveHXFixture:
    """Actual structured p-refined positive auxiliary fixture."""

    def __init__(
        self,
        degree: int,
        comm: MPI.Comm = MPI.COMM_WORLD,
        *,
        variant: str = "sequential-v1",
    ) -> None:
        degree = int(degree)
        if degree not in (2, 3):
            raise ValueError("the focused real L2 fixture supports degree 2 or 3")
        self.degree = degree
        self.comm = comm
        self.variant = variant
        cfg = target_stage4_config(degree=degree, h_nm=50.0)
        self.cfg = cfg
        plan = _stage4_axis_plan(cfg, comm.size)
        self.high_mesh = _structured_hexa_mesh(
            comm,
            plan.x_values,
            plan.y_values,
            plan.z_values,
            preserve_input_partition=cfg.stage4_preserve_structured_input_partition,
        )
        high_facets, _ = _mark_boundary_facets(self.high_mesh, cfg)
        high_cells = _mark_cells(self.high_mesh, cfg)
        self.high_cell_tags = high_cells
        high_data = SimpleNamespace(
            mesh=self.high_mesh,
            cell_tags=high_cells,
            facet_tags=high_facets,
        )
        self.high_space = fem.functionspace(
            self.high_mesh,
            element(
                "N1curl",
                self.high_mesh.basix_cell(),
                degree,
                dtype=default_real_type,
            ),
        )
        self.high_floquet = build_double_floquet_mpc(self.high_space, high_data, cfg)
        (
            self.high_mu_coefficient,
            self.high_mass_coefficient,
            high_coefficient_audit,
        ) = _piecewise_positive_coefficients(self.high_mesh, high_cells, cfg)
        self.mu_inverse = PETSc.ScalarType(abs(1.0 / complex(cfg.mu_r)))
        self.mass_coefficient = PETSc.ScalarType(cfg.k0**2 * abs(cfg.eps_air))
        self.high_coefficient_audit = high_coefficient_audit
        high_u = ufl.TrialFunction(self.high_space)
        high_v = ufl.TestFunction(self.high_space)
        self.high_form = (
            self.high_mu_coefficient * ufl.inner(ufl.curl(high_u), ufl.curl(high_v))
            + self.high_mass_coefficient * ufl.inner(high_u, high_v)
        ) * ufl.dx
        self.high_action = build_fullspace_mpc_form_action(
            self.high_form,
            self.high_space,
            mpc=self.high_floquet.mpc,
        )
        self.high_source = _high_source(self.high_space, self.high_floquet)
        self.high_field = _consistent_field(self.high_space, self.high_floquet)

        refined_axes = tuple(
            _refined_axis(values, degree)
            for values in (plan.x_values, plan.y_values, plan.z_values)
        )
        self.refined_axes = refined_axes
        self.lor_mesh = _structured_hexa_mesh(
            comm,
            *refined_axes,
            preserve_input_partition=cfg.stage4_preserve_structured_input_partition,
        )
        lor_facets, _ = _mark_boundary_facets(self.lor_mesh, cfg)
        lor_cells = _mark_cells(self.lor_mesh, cfg)
        self.lor_cell_tags = lor_cells
        lor_data = SimpleNamespace(
            mesh=self.lor_mesh,
            cell_tags=lor_cells,
            facet_tags=lor_facets,
        )
        low_cfg = target_stage4_config(degree=1, h_nm=50.0)
        self.lor_edge_space = fem.functionspace(
            self.lor_mesh,
            element(
                "N1curl",
                self.lor_mesh.basix_cell(),
                1,
                dtype=default_real_type,
            ),
        )
        self._lor_p1_transfer_local_indices = np.asarray(
            [
                _p1_transfer_local_indices(self.lor_edge_space, cell)
                for cell in range(
                    int(self.lor_mesh.topology.index_map(3).size_local)
                )
            ],
            dtype=np.int32,
        )
        self.lor_node_space = fem.functionspace(
            self.lor_mesh,
            element(
                "Lagrange",
                self.lor_mesh.basix_cell(),
                1,
                dtype=default_real_type,
            ),
        )
        self.lor_edge_floquet = build_double_floquet_mpc(
            self.lor_edge_space, lor_data, low_cfg
        )
        self.lor_node_floquet, node_constraint_audit = _scalar_periodic_mpc(
            self.lor_node_space, low_cfg
        )
        self.lor_node_constraint_audit = node_constraint_audit
        (
            self.lor_mu_coefficient,
            self.lor_mass_coefficient,
            lor_coefficient_audit,
        ) = _piecewise_positive_coefficients(self.lor_mesh, lor_cells, low_cfg)
        self.lor_coefficient_audit = lor_coefficient_audit
        lor_u = ufl.TrialFunction(self.lor_edge_space)
        lor_v = ufl.TestFunction(self.lor_edge_space)
        self.edge_form = (
            self.lor_mu_coefficient * ufl.inner(ufl.curl(lor_u), ufl.curl(lor_v))
            + self.lor_mass_coefficient * ufl.inner(lor_u, lor_v)
        ) * ufl.dx
        node_u = ufl.TrialFunction(self.lor_node_space)
        node_v = ufl.TestFunction(self.lor_node_space)
        self.node_form = (
            self.lor_mu_coefficient * ufl.inner(ufl.grad(node_u), ufl.grad(node_v))
            + self.lor_mass_coefficient * node_u * ufl.conj(node_v)
        ) * ufl.dx
        self.edge_matrix = _assemble_sparse(
            self.edge_form, mpc=self.lor_edge_floquet.mpc
        )
        self.node_matrix = _assemble_sparse(
            self.node_form, mpc=self.lor_node_floquet
        )
        (
            self.gradient,
            map_tail,
            self.de_rham_audit,
            self.lor_edge_records,
        ) = _de_rham_maps(
            self.lor_edge_space,
            self.lor_node_space,
            self.lor_edge_floquet.mpc,
            self.lor_node_floquet,
            self.edge_matrix,
            self.node_matrix,
        )
        self.gradient_adjoint = map_tail[0]
        self.vector_prolongations = tuple(map_tail[1:])
        self.vector_restrictions = tuple(
            _hermitian_transpose(matrix) for matrix in self.vector_prolongations
        )
        from .fullspace_lor_native_hx import NativeComplexLORHX

        self.hx = NativeComplexLORHX(
            self.edge_matrix,
            self.node_matrix,
            self.gradient,
            self.gradient_adjoint,
            self.vector_prolongations,
            self.vector_restrictions,
            variant=variant,
        )
        self.lor_source = _high_source(self.lor_edge_space, self.lor_edge_floquet)
        self.reference_transfer = build_reference_factor_lor_transfer(degree)
        self.lor_p1_transfer = _P1IdentityTransfer()
        self.lor_raw_topology = build_canonical_lor_subedge_topology(
            self.lor_edge_space,
            self.lor_edge_floquet,
            self.lor_p1_transfer,
        )
        self.roundtrip, self.lor_owner_packet, self.transfer_error, self.lor_topology = (
            global_lor_edge_roundtrip(
                self.high_space,
                self.high_floquet,
                self.high_field,
                self.reference_transfer,
            )
        )
        self.transfer_input_norm = float(self.high_field.x.petsc_vec.norm())
        self.transfer_owner_packet_norm = float(
            np.linalg.norm(np.asarray(self.lor_owner_packet[1], dtype=np.complex128))
        )
        self.audit = self._make_audit()

    def _make_audit(self) -> dict[str, Any]:
        comm = self.comm
        edge_map = self.lor_edge_space.dofmap.index_map
        node_map = self.lor_node_space.dofmap.index_map
        high_map = self.high_space.dofmap.index_map
        high_cells = int(
            comm.allreduce(
                self.high_mesh.topology.index_map(self.high_mesh.topology.dim).size_local,
                op=MPI.SUM,
            )
        )
        lor_cells = int(
            comm.allreduce(
                self.lor_mesh.topology.index_map(self.lor_mesh.topology.dim).size_local,
                op=MPI.SUM,
            )
        )
        edge_slave = int(self.lor_edge_floquet.num_local_slaves)
        edge_slave = int(comm.allreduce(edge_slave, op=MPI.SUM))
        node_slave = int(self.lor_node_constraint_audit["global_slave_rows"])
        return {
            "schema": (
                "task038.l2.real-positive-hx-fixture.v2"
                if self.variant == "additive-v2"
                else "task038.l2.real-positive-hx-fixture.v1"
            ),
            "variant": self.variant,
            "degree": self.degree,
            "high_cell_count": high_cells,
            "lor_cell_count": lor_cells,
            "high_space_global_rows": int(high_map.size_global),
            "lor_full_edge_rows": int(edge_map.size_global),
            "lor_full_node_rows": int(node_map.size_global),
            "lor_edge_slave_rows": edge_slave,
            "lor_node_slave_rows": node_slave,
            "full_space_slave_identity_rows": True,
            "canonical_only_reduction": False,
            "high_order_matrix_free": True,
            "high_order_global_aij": False,
            "lor_edge_matrix_type": str(self.edge_matrix.getType()),
            "lor_node_matrix_type": str(self.node_matrix.getType()),
            "global_transfer_matrix": False,
            "global_numeric_allgather": False,
            "metadata_allgather": False,
            "metadata_exchange": "boundary_scalar_keys_and_owned_needed_ghost_rows",
            "de_rham_map_audit": self.de_rham_audit,
            "phase_application": "finalized_floquet_mpc_once",
            "slave_master_complete": True,
            "mu_inverse": [float(self.mu_inverse.real), float(self.mu_inverse.imag)],
            "k0_squared_abs_epsilon": float(self.mass_coefficient.real),
            "piecewise_coefficients": {
                "high": self.high_coefficient_audit,
                "lor": self.lor_coefficient_audit,
            },
            "single_cell_transfer_work_identity_relative": float(
                _local_transfer_work_identity(self.degree)
            ),
            "global_residual_transfer_work_identity": "test_measured_separately",
            "transfer_roundtrip_relative": float(self.transfer_error),
            "transfer_input_norm": self.transfer_input_norm,
            "transfer_owner_packet_norm": self.transfer_owner_packet_norm,
            "transfer_nonzero_source": bool(
                self.transfer_input_norm > 0.0
                and self.transfer_owner_packet_norm > 0.0
            ),
            "residual_transfer_scope": "global_owner_routed_adjoint_and_primal",
            "high_action_audit": self.high_action.audit,
            "hx_audit": self.hx.audit,
        }

    def build_l2_source(self, name: str) -> tuple[PETSc.Vec, dict[str, Any]]:
        """Build one frozen, finalized-MPC primal source for the L2 oracle."""

        formula = l2_source_formula(name)
        function = fem.Function(self.high_floquet.mpc.function_space)
        vector = function.x.petsc_vec
        function.interpolate(
            lambda coordinates: _l2_analytic_values(name, coordinates, self.cfg)
        )
        function.x.scatter_forward()
        self.high_floquet.mpc.homogenize(function)
        function.x.scatter_forward()
        result = vector.copy()
        del function
        return result, {
            "name": name,
            "formula": formula,
            "phase_application": "algebraic_slave_zero_action_internal_finalized_mpc_once",
            "primal_role": "full_fe",
        }

    def apply_high_action_copy(self, source: PETSc.Vec) -> PETSc.Vec:
        """Copy the borrowed matrix-free action result without destroying it."""

        return self.high_action.apply(source).copy()

    def apply_high(self) -> tuple[PETSc.Vec, PETSc.Vec]:
        first = self.high_action.apply(self.high_source).copy()
        second = self.high_action.apply(self.high_source).copy()
        return first, second

    def apply_lor(self) -> tuple[PETSc.Vec, PETSc.Vec]:
        first = self.hx.apply(self.lor_source)
        second = self.hx.apply(self.lor_source)
        return first, second

    def _local_node_coordinates(self) -> dict[int, np.ndarray]:
        space = self.lor_node_space
        index_map = space.dofmap.index_map
        storage_count = int(index_map.size_local + index_map.num_ghosts)
        coordinates = np.asarray(space.tabulate_dof_coordinates(), dtype=np.float64)
        global_ids = np.asarray(
            index_map.local_to_global(np.arange(storage_count, dtype=np.int32)),
            dtype=np.int64,
        )
        return {
            int(global_ids[index]): np.asarray(coordinates[index], dtype=np.float64)
            for index in range(storage_count)
        }

    def _raw_edge_canonical_map(self) -> dict[int, tuple[int, int]]:
        node_coordinates = self._local_node_coordinates()
        upper = np.asarray([axis.size - 1 for axis in self.refined_axes], dtype=np.int32)
        result: dict[int, tuple[int, int]] = {}
        for edge_gid, (low_gid, high_gid, _length, _axis) in self.lor_edge_records.items():
            low = node_coordinates[int(low_gid)]
            high = node_coordinates[int(high_gid)]
            start = np.asarray(
                [int(np.argmin(np.abs(axis - low[index]))) for index, axis in enumerate(self.refined_axes)],
                dtype=np.int32,
            )
            end = np.asarray(
                [int(np.argmin(np.abs(axis - high[index]))) for index, axis in enumerate(self.refined_axes)],
                dtype=np.int32,
            )
            ids, _orientation, phase = _pack_canonical_edges(
                start[None, :], end[None, :], upper
            )
            result[int(edge_gid)] = (int(ids[0]), int(phase[0]))
        owned = set(
            int(value)
            for value in self.lor_edge_space.dofmap.index_map.local_to_global(
                np.arange(
                    int(self.lor_edge_space.dofmap.index_map.size_local),
                    dtype=np.int32,
                )
            )
        )
        if set(result) != owned:
            raise RuntimeError("raw LOR owned edge canonical map does not close")
        return result

    def _route_low_owner_packet(
        self, vector: PETSc.Vec
    ) -> tuple[np.ndarray, np.ndarray]:
        """Route a low primal vector once to the canonical edge owners."""

        work_space = self.lor_edge_floquet.mpc.function_space
        field = fem.Function(work_space)
        owned = int(work_space.dofmap.index_map.size_local)
        field.x.petsc_vec.set(0.0 + 0.0j)
        field.x.petsc_vec.array[:owned] = np.asarray(
            vector.array[:owned], dtype=np.complex128
        )
        field.x.scatter_forward()
        self.lor_edge_floquet.mpc.homogenize(field)
        field.x.scatter_forward()
        self.lor_edge_floquet.mpc.backsubstitution(field)
        field.x.scatter_forward()
        cell_count = int(self.lor_mesh.topology.index_map(3).size_local)
        cell_info = np.asarray(
            self.lor_mesh.topology.get_cell_permutation_info(), dtype=np.uint32
        )

        def chunks():
            batch_start = 0
            batch: list[np.ndarray] = []
            for cell in range(cell_count):
                local_dofs = np.asarray(
                    work_space.dofmap.cell_dofs(cell), dtype=np.int32
                )
                values = np.asarray(field.x.array[local_dofs], dtype=np.complex128).copy()
                work_space.element.Tt_apply(
                    values, np.asarray([cell_info[cell]], dtype=np.uint32), 1
                )
                values = values[self._lor_p1_transfer_local_indices[cell]]
                batch.append(values)
                if len(batch) == 32 or cell + 1 == cell_count:
                    yield batch_start, np.asarray(batch, dtype=np.complex128)
                    batch_start = cell + 1
                    batch = []

        owner_ids, owner_values = self.lor_raw_topology.route_owner_cell_chunks(chunks())
        del field
        return owner_ids, owner_values

    def _reconstruct_high_from_unique(self, unique_values: np.ndarray) -> PETSc.Vec:
        work_space = self.high_floquet.mpc.function_space
        field = fem.Function(work_space)
        multiplicity = fem.Function(work_space)
        field.x.array[:] = 0.0
        multiplicity.x.array[:] = 0.0
        cell_count = int(self.high_mesh.topology.index_map(3).size_local)
        cell_info = np.asarray(
            self.high_mesh.topology.get_cell_permutation_info(), dtype=np.uint32
        )
        for cell_start in range(0, cell_count, 32):
            cell_end = min(cell_start + 32, cell_count)
            pulled = self.lor_topology.cell_values_from_unique(
                unique_values, cell_start, cell_end
            )
            restored = self.reference_transfer.lor_to_high_many(pulled)
            for offset, cell in enumerate(range(cell_start, cell_end)):
                local_dofs = np.asarray(
                    work_space.dofmap.cell_dofs(cell), dtype=np.int32
                )
                values = restored[offset].copy()
                work_space.element.T_apply(
                    values, np.asarray([cell_info[cell]], dtype=np.uint32), 1
                )
                field.x.array[local_dofs] += values
                multiplicity.x.array[local_dofs] += 1.0
        field.x.petsc_vec.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
        )
        multiplicity.x.petsc_vec.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
        )
        owned = int(work_space.dofmap.index_map.size_local)
        if np.any(multiplicity.x.array[:owned] <= 0.0):
            raise RuntimeError("high reconstruction has an uncovered owned row")
        field.x.array[:owned] /= multiplicity.x.array[:owned]
        field.x.petsc_vec.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD
        )
        self.high_floquet.mpc.backsubstitution(field)
        self.high_floquet.mpc.homogenize(field)
        field.x.scatter_forward()
        result = field.x.petsc_vec.copy()
        del multiplicity
        del field
        return result

    def _dual_restrict(
        self, residual_field: Any
    ) -> tuple[np.ndarray, np.ndarray]:
        """Apply the adjoint transfer and reduce shared LOR edges at owners."""

        work_space = self.high_floquet.mpc.function_space
        multiplicity = fem.Function(work_space)
        multiplicity.x.array[:] = 0.0
        cell_info = np.asarray(
            self.high_mesh.topology.get_cell_permutation_info(), dtype=np.uint32
        )
        cell_count = int(self.high_mesh.topology.index_map(3).size_local)
        for cell in range(cell_count):
            local_dofs = np.asarray(
                work_space.dofmap.cell_dofs(cell), dtype=np.int32
            )
            multiplicity.x.array[local_dofs] += 1.0
        multiplicity.x.petsc_vec.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
        )
        multiplicity.x.scatter_forward()
        def chunks():
            batch_start = 0
            batch: list[np.ndarray] = []
            for cell in range(cell_count):
                local_dofs = np.asarray(
                    work_space.dofmap.cell_dofs(cell), dtype=np.int32
                )
                local_multiplicity = np.asarray(
                    multiplicity.x.array[local_dofs].real, dtype=np.float64
                )
                if np.any(local_multiplicity <= 0.0):
                    raise RuntimeError("high reconstruction multiplicity is incomplete")
                canonical_dual = np.asarray(
                    residual_field.x.array[local_dofs], dtype=np.complex128
                ).copy() / local_multiplicity
                work_space.element.Tt_apply(
                    canonical_dual, np.asarray([cell_info[cell]], dtype=np.uint32), 1
                )
                batch.append(canonical_dual)
                if len(batch) == 32 or cell + 1 == cell_count:
                    yield batch_start, self.reference_transfer.lor_to_high_adjoint_many(
                        np.asarray(batch, dtype=np.complex128)
                    )
                    batch_start = cell + 1
                    batch = []

        owner_ids, owner_values = self.lor_topology.route_owner_cell_chunks_additive(
            chunks()
        )
        del multiplicity
        return owner_ids, owner_values

    def _full_lor_dual_vector_from_high_owner_packet(
        self, high_owner_ids: np.ndarray, high_owner_values: np.ndarray
    ) -> PETSc.Vec:
        """Pull a high owner packet directly into the low topology."""

        low_ids = np.asarray(self.lor_raw_topology.unique_edge_ids, dtype=np.uint32)
        low_owned_ids = np.asarray(self.lor_raw_topology.owned_edge_ids, dtype=np.uint32)
        if not np.array_equal(high_owner_ids, low_owned_ids):
            raise RuntimeError("canonical owner inventories differ between LOR topologies")
        low_unique = self.lor_raw_topology.pull_owner_unique_values(
            high_owner_ids, high_owner_values
        )
        raw_map = self._raw_edge_canonical_map()
        vector = self.edge_matrix.createVecRight()
        start, stop = vector.getOwnershipRange()
        for global_id in range(int(start), int(stop)):
            canonical_id, phase_code = raw_map[global_id]
            position = int(np.searchsorted(low_ids, canonical_id))
            if position >= low_ids.size or int(low_ids[position]) != canonical_id:
                raise RuntimeError("raw LOR dual row has no canonical owner value")
            vector.array[global_id - int(start)] = (
                low_unique[position] if int(phase_code) == 0 else 0.0
            )
        return vector

    def _restrict_high_dual(
        self, vector: PETSc.Vec
    ) -> tuple[np.ndarray, np.ndarray]:
        """Restrict a high full-space dual after removing slave rows."""

        work_space = self.high_floquet.mpc.function_space
        field = fem.Function(work_space)
        owned = int(work_space.dofmap.index_map.size_local)
        field.x.petsc_vec.set(0.0 + 0.0j)
        field.x.petsc_vec.array[:owned] = np.asarray(
            vector.array[:owned], dtype=np.complex128
        )
        field.x.scatter_forward()
        self.high_floquet.mpc.homogenize(field)
        field.x.scatter_forward()
        result = self._dual_restrict(field)
        del field
        return result

    def apply_high_preconditioner(self, residual: PETSc.Vec) -> PETSc.Vec:
        """Apply the owner-local LOR HX preconditioner to a high residual."""

        high_owner_ids, high_owner_values = self._restrict_high_dual(residual)
        low_input = self._full_lor_dual_vector_from_high_owner_packet(
            high_owner_ids, high_owner_values
        )
        low_output = self.hx.apply(low_input)
        low_owner_ids, low_owner_values = self._route_low_owner_packet(low_output)
        high_owned_ids = np.asarray(self.lor_topology.owned_edge_ids, dtype=np.uint32)
        if not np.array_equal(low_owner_ids, high_owned_ids):
            raise RuntimeError("canonical owner inventories differ between LOR topologies")
        high_unique = self.lor_topology.pull_owner_unique_values(
            low_owner_ids, low_owner_values
        )
        result = self._reconstruct_high_from_unique(high_unique)
        low_input.destroy()
        low_output.destroy()
        return result

    def apply_residual_through_lor(self) -> PETSc.Vec:
        """Test-only wrapper using the production high preconditioner entry point."""

        residual = self.high_action.apply(self.high_source).copy()
        try:
            return self.apply_high_preconditioner(residual)
        finally:
            residual.destroy()

    def destroy(self) -> None:
        for vector_name in ("high_source", "lor_source"):
            vector = getattr(self, vector_name, None)
            if vector is not None:
                vector.destroy()
                setattr(self, vector_name, None)
        field = getattr(self, "high_field", None)
        if field is not None:
            del field
            self.high_field = None
        for name in ("high_action", "hx"):
            obj = getattr(self, name, None)
            if obj is not None:
                obj.destroy()
                setattr(self, name, None)
        for name in (
            "edge_matrix",
            "node_matrix",
            "gradient",
            "gradient_adjoint",
            *[f"_vector_prolongation_{axis}" for axis in "xyz"],
        ):
            obj = getattr(self, name, None)
            if obj is not None and hasattr(obj, "destroy"):
                obj.destroy()
                setattr(self, name, None)
        for matrix in getattr(self, "vector_prolongations", ()):
            matrix.destroy()
        for matrix in getattr(self, "vector_restrictions", ()):
            matrix.destroy()
        self.vector_prolongations = ()
        self.vector_restrictions = ()
        self.reference_transfer = None
        self.lor_p1_transfer = None
        self.roundtrip = None


class L2HighActionShellContext:
    """Matrix-free B_h shell that copies, never destroys, action outputs."""

    def __init__(self, fixture: RealL2PositiveHXFixture) -> None:
        self.fixture = fixture

    def mult(
        self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        result = self.fixture.apply_high_action_copy(source)
        try:
            result.copy(target)
        finally:
            result.destroy()


class L2HXPCContext:
    """Python PC shell for one fixed owner-local HX application."""

    def __init__(self, fixture: RealL2PositiveHXFixture) -> None:
        self.fixture = fixture
        self.apply_count = 0

    def apply(
        self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        result = self.fixture.apply_high_preconditioner(source)
        try:
            result.copy(target)
        finally:
            result.destroy()
        self.apply_count += 1


def build_l2_high_action_shell(
    fixture: RealL2PositiveHXFixture,
) -> tuple[PETSc.Mat, L2HighActionShellContext]:
    """Create the matrix-free high-order B_h shell used by fixed CG."""

    context = L2HighActionShellContext(fixture)
    matrix = PETSc.Mat().createPython(
        fixture.high_action.matrix.getSizes(),
        context=context,
        comm=fixture.comm,
    )
    matrix.setUp()
    return matrix, context


def build_l2_cg_solver(
    fixture: RealL2PositiveHXFixture,
) -> tuple[PETSc.KSP, PETSc.Mat, L2HXPCContext]:
    """Build the frozen zero-guess CG + Python-HX shell solver."""

    operator, _operator_context = build_l2_high_action_shell(fixture)
    pc_context = L2HXPCContext(fixture)
    ksp = PETSc.KSP().create(fixture.comm)
    ksp.setOperators(operator)
    ksp.setType("cg")
    ksp.setInitialGuessNonzero(False)
    ksp.setTolerances(rtol=L2_CG_RTOL, atol=0.0, max_it=L2_CG_MAX_IT)
    ksp.setPCSide(PETSc.PC.Side.LEFT)
    pc = ksp.getPC()
    pc.setType("python")
    pc.setPythonContext(pc_context)
    ksp.setUp()
    return ksp, operator, pc_context


def l2_one_apply(
    fixture: RealL2PositiveHXFixture, primal_source: PETSc.Vec
) -> dict[str, Any]:
    """Form r=B_h u and apply M_H^{-1} once to a primal source u."""

    input_before = np.asarray(
        primal_source.getArray(readonly=True), dtype=np.complex128
    ).copy()
    residual = fixture.apply_high_action_copy(primal_source)
    output = fixture.apply_high_preconditioner(residual)
    applied_output = fixture.apply_high_action_copy(output)
    true_residual = residual.copy()
    true_residual.axpy(PETSc.ScalarType(-1.0), applied_output)
    residual_norm = float(residual.norm())
    rho = float(true_residual.norm() / max(residual_norm, np.finfo(float).tiny))
    input_unchanged = bool(
        np.array_equal(
            input_before,
            np.asarray(primal_source.getArray(readonly=True), dtype=np.complex128),
        )
    )
    return {
        "residual": residual,
        "output": output,
        "applied_output": applied_output,
        "true_residual": true_residual,
        "rho": rho,
        "input_unchanged": input_unchanged,
        "residual_norm": residual_norm,
    }


def solve_l2_cg(
    fixture: RealL2PositiveHXFixture, rhs: PETSc.Vec
) -> dict[str, Any]:
    """Run the fixed CG shell once and return owned resources plus true facts."""

    ksp, operator, pc_context = build_l2_cg_solver(fixture)
    solution = operator.createVecRight()
    solution.set(0.0 + 0.0j)
    ksp.solve(rhs, solution)
    action = fixture.apply_high_action_copy(solution)
    true_residual = rhs.copy()
    true_residual.axpy(PETSc.ScalarType(-1.0), action)
    rhs_norm = float(rhs.norm())
    return {
        "ksp": ksp,
        "operator": operator,
        "pc_context": pc_context,
        "solution": solution,
        "action": action,
        "true_residual": true_residual,
        "reason": int(ksp.getConvergedReason()),
        "iterations": int(ksp.getIterationNumber()),
        "reported_residual_norm": float(ksp.getResidualNorm()),
        "true_residual_relative": float(
            true_residual.norm() / max(rhs_norm, np.finfo(float).tiny)
        ),
    }


def destroy_l2_cg_result(result: dict[str, Any]) -> None:
    """Release the vectors, shell and KSP returned by :func:`solve_l2_cg`."""

    for name in ("true_residual", "action", "solution"):
        vector = result.pop(name, None)
        if vector is not None:
            vector.destroy()
    ksp = result.pop("ksp", None)
    if ksp is not None:
        ksp.destroy()
    operator = result.pop("operator", None)
    if operator is not None:
        operator.destroy()


def _local_transfer_work_identity(degree: int) -> float:
    """Bounded single-cell residual restriction/primal reconstruction oracle."""

    transfer = build_local_lor_transfer(int(degree))
    rng = np.random.default_rng(20260823)
    high_size = int(transfer.high_to_lor_matrix.shape[1])
    lor_size = int(transfer.high_to_lor_matrix.shape[0])
    high = rng.standard_normal(high_size) + 1j * rng.standard_normal(
        high_size
    )
    residual = rng.standard_normal(lor_size) + 1j * rng.standard_normal(
        lor_size
    )
    mapped = transfer.high_to_lor(high)
    lhs = np.vdot(mapped, residual)
    rhs = np.vdot(high, transfer.high_to_lor_matrix.conj().T @ residual)
    result = float(abs(lhs - rhs) / max(abs(lhs), abs(rhs), np.finfo(float).tiny))
    del transfer
    return result


def build_real_l2_positive_hx_fixture(
    degree: int,
    comm: MPI.Comm = MPI.COMM_WORLD,
    *,
    variant: str = "sequential-v1",
) -> RealL2PositiveHXFixture:
    return RealL2PositiveHXFixture(degree, comm, variant=variant)


__all__ = (
    "L2_CG_MAX_IT",
    "L2_CG_RTOL",
    "L2_RHO_LIMITS",
    "L2_SOURCE_NAMES",
    "L2_REPEAT_LIMIT",
    "L2HXPCContext",
    "L2HighActionShellContext",
    "RealL2PositiveHXFixture",
    "build_l2_cg_solver",
    "build_l2_high_action_shell",
    "build_real_l2_positive_hx_fixture",
    "destroy_l2_cg_result",
    "l2_one_apply",
    "l2_source_formula",
    "solve_l2_cg",
)
