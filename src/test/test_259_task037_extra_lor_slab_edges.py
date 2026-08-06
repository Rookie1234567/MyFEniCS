from __future__ import annotations

import basix
import numpy as np
import pytest

from src.constraints.high_order_floquet_trace import (
    FloquetTopologyKey,
    FloquetTraceTopology,
    PhaseIndependentConstraintBlock,
)
from src.geometry.tetra_mesh_audit import (
    canonical_entity_key,
    canonical_point_key,
)
from src.solvers.static_lor_hcurl_transfer import (
    build_affine_lor_parent_topology,
    build_lor_slab_edge_space,
)


_TOLERANCE = 1.0e-12
_MACRO_EDGE_PAIRS = (
    (0, 1),
    (0, 2),
    (0, 4),
    (1, 3),
    (1, 5),
    (2, 3),
    (2, 6),
    (3, 7),
    (4, 5),
    (4, 6),
    (5, 7),
    (6, 7),
)


def _parent_vertices(translation=(0.0, 0.0, 0.0)) -> np.ndarray:
    return basix.geometry(basix.CellType.hexahedron) + np.asarray(
        translation,
        dtype=np.float64,
    )


def _topology(degree: int, cell_id: int, translation=(0.0, 0.0, 0.0)):
    return build_affine_lor_parent_topology(
        _parent_vertices(translation),
        degree=degree,
        canonical_cell_id=cell_id,
        material_tag=3,
        cell_permutation=0,
        coordinate_tolerance=_TOLERANCE,
    )


def _empty_floquet(degree: int) -> FloquetTraceTopology:
    return FloquetTraceTopology(
        key=FloquetTopologyKey(
            mesh_token=f"empty-{degree}",
            element_family="N1curl",
            degree=degree,
        ),
        blocks=(),
        topology_build_seconds=0.0,
        bytes_sent=0,
        bytes_received=0,
    )


def _entity_key(points) -> tuple[tuple[int, int, int], ...]:
    return canonical_entity_key(np.asarray(points, dtype=np.float64), _TOLERANCE)


def _periodic_block(
    *,
    kind: str,
    entity_kind: str,
    slave_points,
    master_points,
    identifier: int,
    transform_value: complex,
) -> PhaseIndependentConstraintBlock:
    dimension = 1 if entity_kind == "edge" else 2
    kind_code = {"x": 1, "y": 2, "corner": 3}[kind]
    vertex_count = 2 if entity_kind == "edge" else 4
    return PhaseIndependentConstraintBlock(
        kind=kind,
        slave_global_dofs=(identifier,),
        master_global_dofs=(identifier + 1000,),
        coefficient_transform=np.asarray([[transform_value]], dtype=np.complex128),
        entity_kind=entity_kind,
        slave_entity_id=identifier,
        master_entity_id=identifier + 1000,
        slave_entity_geometry_key=_entity_key(slave_points),
        master_entity_geometry_key=_entity_key(master_points),
        periodic_pair_key=(dimension, kind_code, 0, 0, 0, 0),
        entity_vertex_permutation=tuple(range(vertex_count)),
        cell_type="hexahedron",
    )


def _synthetic_floquet(
    degree: int,
    *,
    transform_value: complex = 91.0 + 37.0j,
    reverse_blocks: bool = False,
) -> FloquetTraceTopology:
    vertices = basix.geometry(basix.CellType.hexahedron)
    blocks = []
    identifier = 1
    for first, second in _MACRO_EDGE_PAIRS:
        edge_vertices = vertices[[first, second]]
        midpoint = np.mean(edge_vertices, axis=0)
        x_boundary = np.isclose(midpoint[0], 1.0)
        y_boundary = np.isclose(midpoint[1], 1.0)
        if not x_boundary and not y_boundary:
            continue
        kind = "corner" if x_boundary and y_boundary else "x" if x_boundary else "y"
        translation = np.asarray(
            (1.0 if x_boundary else 0.0, 1.0 if y_boundary else 0.0, 0.0)
        )
        blocks.append(
            _periodic_block(
                kind=kind,
                entity_kind="edge",
                slave_points=edge_vertices,
                master_points=edge_vertices - translation,
                identifier=identifier,
                transform_value=transform_value,
            )
        )
        identifier += 1
    x_face_master = [
        (0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 1.0, 1.0),
    ]
    x_face_slave = [
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (1.0, 0.0, 1.0),
        (1.0, 1.0, 1.0),
    ]
    y_face_master = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 0.0, 1.0),
    ]
    y_face_slave = [
        (0.0, 1.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 1.0),
        (1.0, 1.0, 1.0),
    ]
    blocks.extend(
        (
            _periodic_block(
                kind="x",
                entity_kind="face",
                slave_points=x_face_slave,
                master_points=x_face_master,
                identifier=identifier,
                transform_value=transform_value,
            ),
            _periodic_block(
                kind="y",
                entity_kind="face",
                slave_points=y_face_slave,
                master_points=y_face_master,
                identifier=identifier + 1,
                transform_value=transform_value,
            ),
        )
    )
    blocks = tuple(blocks)
    if reverse_blocks:
        blocks = blocks[::-1]
    return FloquetTraceTopology(
        key=FloquetTopologyKey(
            mesh_token=f"double-periodic-{degree}",
            element_family="N1curl",
            degree=degree,
        ),
        blocks=blocks,
        topology_build_seconds=0.0,
        bytes_sent=0,
        bytes_received=0,
    )


def _edge_keys_on_parent_edge(topology, face_ids):
    required = set(face_ids)
    return tuple(
        key
        for key, faces in zip(
            topology.edge_keys,
            topology.edge_boundary_faces,
            strict=True,
        )
        if required.issubset(faces)
    )


def _translated(edge_key, delta):
    return tuple(
        sorted(
            tuple(int(point[axis]) + int(delta[axis]) for axis in range(3))
            for point in edge_key
        )
    )


@pytest.mark.parametrize("degree, shared_edges", ((2, 12), (3, 24)))
def test_multi_parent_edge_inventory_is_sorted_and_deduplicated(
    degree: int,
    shared_edges: int,
):
    left = _topology(degree, 10)
    right = _topology(degree, 2, (1.0, 0.0, 0.0))
    space = build_lor_slab_edge_space(
        [right, left],
        _empty_floquet(degree),
        phase_x=1.0 + 0.0j,
        phase_y=1.0 + 0.0j,
    )
    expected_shared = set(left.edge_keys).intersection(right.edge_keys)
    assert len(expected_shared) == shared_edges
    assert space.parent_ids == (2, 10)
    assert len(space.physical_edge_keys) == 2 * len(left.edge_keys) - shared_edges
    assert space.active_edge_keys == space.physical_edge_keys
    for matrix, topology in zip(space._parent_expansions, (right, left), strict=True):
        assert matrix.shape == (len(topology.edge_keys), len(space.active_edge_keys))
        assert np.all(np.diff(matrix.indptr) == 1)
        assert matrix.nnz == len(topology.edge_keys)
    repeated = build_lor_slab_edge_space(
        [left, right],
        _empty_floquet(degree),
        phase_x=1.0 + 0.0j,
        phase_y=1.0 + 0.0j,
    )
    assert repeated.parent_ids == space.parent_ids
    assert repeated.physical_edge_keys == space.physical_edge_keys
    assert repeated.active_edge_keys == space.active_edge_keys
    for first, second in zip(
        space._parent_expansions,
        repeated._parent_expansions,
        strict=True,
    ):
        assert np.array_equal(first.indptr, second.indptr)
        assert np.array_equal(first.indices, second.indices)
        assert np.array_equal(first.data, second.data)

    rng = np.random.default_rng(2590 + degree)
    active_values = rng.normal(size=len(space.active_edge_keys)) + 1j * rng.normal(
        size=len(space.active_edge_keys)
    )
    parent_values = [
        rng.normal(size=matrix.shape[0]) + 1j * rng.normal(size=matrix.shape[0])
        for matrix in space._parent_expansions
    ]
    left = sum(
        np.vdot(matrix @ active_values, values)
        for matrix, values in zip(
            space._parent_expansions,
            parent_values,
            strict=True,
        )
    )
    right = np.vdot(active_values, space.apply_adjoint(parent_values))
    assert abs(left - right) / max(abs(left), abs(right), np.finfo(float).tiny) <= 1.0e-11


@pytest.mark.parametrize("degree", (2, 3))
def test_periodic_edges_faces_phase_adjoint_and_dummy_transform_ignored(degree: int):
    topology = _topology(degree, 7)
    phase_x = np.exp(0.23j)
    phase_y = np.exp(-0.41j)
    floquet = _synthetic_floquet(degree)
    assert sum(block.entity_kind == "edge" for block in floquet.blocks) == 7
    assert sum(block.entity_kind == "face" for block in floquet.blocks) == 2
    space = build_lor_slab_edge_space(
        [topology],
        floquet,
        phase_x=phase_x,
        phase_y=phase_y,
    )
    assert len(space.active_edge_keys) + space.audit["periodic_slave_edge_count"] == len(
        space.physical_edge_keys
    )
    assert space.audit["high_order_coefficient_transform_used"] is False
    assert np.all(np.diff(space._parent_expansions[0].indptr) == 1)
    periodic_boundary_keys = {
        key
        for key, faces in zip(
            topology.edge_keys,
            topology.edge_boundary_faces,
            strict=True,
        )
        if 3 in faces or 4 in faces
    }
    assert periodic_boundary_keys == (
        set(space.physical_edge_keys) - set(space.active_edge_keys)
    )
    assert len(space.active_edge_keys) + len(periodic_boundary_keys) == len(
        space.physical_edge_keys
    )

    active_index = {key: index for index, key in enumerate(space.active_edge_keys)}
    unit = np.asarray(
        canonical_point_key(np.asarray((1.0, 0.0, 0.0)), _TOLERANCE),
        dtype=np.int64,
    )
    x_delta = tuple(-int(value) for value in unit)
    y_delta = tuple(-int(value) for value in unit[[1, 0, 2]])
    expected_relations = (
        (
            _edge_keys_on_parent_edge(topology, (1, 3)),
            x_delta,
            phase_x,
        ),
        (
            _edge_keys_on_parent_edge(topology, (2, 4)),
            y_delta,
            phase_y,
        ),
        (
            _edge_keys_on_parent_edge(topology, (3, 4)),
            tuple(x_delta[axis] + y_delta[axis] for axis in range(3)),
            phase_x * phase_y,
        ),
    )
    matrix = space._parent_expansions[0]
    for slave_keys, delta, expected_coefficient in expected_relations:
        assert slave_keys
        for slave_key in slave_keys:
            master_key = _translated(slave_key, delta)
            active_values = np.zeros(len(space.active_edge_keys), dtype=np.complex128)
            active_values[active_index[master_key]] = 1.0
            row = topology.edge_keys.index(slave_key)
            expanded = space.expand_parent(7, active_values)
            assert np.isclose(expanded[row], expected_coefficient)
            assert np.count_nonzero(np.abs(matrix.getrow(row).data) > 0.0) == 1

    x_face_interior = [
        key
        for key, faces in zip(
            topology.edge_keys,
            topology.edge_boundary_faces,
            strict=True,
        )
        if faces == (3,)
    ]
    assert x_face_interior
    for slave_key in x_face_interior:
        active_values = np.zeros(len(space.active_edge_keys), dtype=np.complex128)
        active_values[active_index[_translated(slave_key, x_delta)]] = 1.0
        row = topology.edge_keys.index(slave_key)
        assert np.isclose(space.expand_parent(7, active_values)[row], phase_x)

    y_face_interior = [
        key
        for key, faces in zip(
            topology.edge_keys,
            topology.edge_boundary_faces,
            strict=True,
        )
        if faces == (4,)
    ]
    assert y_face_interior
    for slave_key in y_face_interior:
        active_values = np.zeros(len(space.active_edge_keys), dtype=np.complex128)
        active_values[active_index[_translated(slave_key, y_delta)]] = 1.0
        row = topology.edge_keys.index(slave_key)
        assert np.isclose(space.expand_parent(7, active_values)[row], phase_y)

    nonperiodic = next(
        key for key in space.physical_edge_keys if key in space.active_edge_keys
    )
    active_values = np.zeros(len(space.active_edge_keys), dtype=np.complex128)
    active_values[active_index[nonperiodic]] = 1.0
    row = topology.edge_keys.index(nonperiodic)
    assert np.isclose(space.expand_parent(7, active_values)[row], 1.0)

    rng = np.random.default_rng(259 + degree)
    active_values = rng.normal(size=len(space.active_edge_keys)) + 1j * rng.normal(
        size=len(space.active_edge_keys)
    )
    parent_values = [
        rng.normal(size=len(topology.edge_keys))
        + 1j * rng.normal(size=len(topology.edge_keys))
    ]
    left = np.vdot(space.expand_parent(7, active_values), parent_values[0])
    right = np.vdot(active_values, space.apply_adjoint(parent_values))
    assert abs(left - right) / max(abs(left), abs(right), np.finfo(float).tiny) <= 1.0e-11

    changed_transform = build_lor_slab_edge_space(
        [topology],
        _synthetic_floquet(degree, transform_value=-17.0 + 29.0j, reverse_blocks=True),
        phase_x=phase_x,
        phase_y=phase_y,
    )
    assert changed_transform.active_edge_keys == space.active_edge_keys
    first = space._parent_expansions[0]
    second = changed_transform._parent_expansions[0]
    assert np.array_equal(first.indptr, second.indptr)
    assert np.array_equal(first.indices, second.indices)
    assert np.array_equal(first.data, second.data)
