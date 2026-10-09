from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np

from src.geometry.task40_v20_geometry import (
    _facet_pair_inventory,
    _mesh_cell_classes,
)


class _Topology:
    def __init__(self, *, cell_count=1):
        self.dim = 3
        self.cell_count = cell_count
        self.permutation_creations = 0

    def index_map(self, dimension):
        assert dimension == 3
        return SimpleNamespace(size_local=self.cell_count)

    def create_entity_permutations(self):
        self.permutation_creations += 1

    def get_cell_permutation_info(self):
        assert self.permutation_creations > 0
        return np.full(self.cell_count, 7, dtype=np.uint32)

    def create_connectivity(self, source_dimension, target_dimension):
        assert (source_dimension, target_dimension) == (2, 3)

    def connectivity(self, source_dimension, target_dimension):
        assert (source_dimension, target_dimension) == (2, 3)
        return SimpleNamespace(links=lambda _facet: np.asarray([0], dtype=np.int32))


def _cube_vertices(x0, x1, y0=0.0, y1=1.0, z0=0.0, z1=1.0):
    return np.asarray(
        [
            [x0, y0, z0],
            [x1, y0, z0],
            [x0, y1, z0],
            [x1, y1, z0],
            [x0, y0, z1],
            [x1, y0, z1],
            [x0, y1, z1],
            [x1, y1, z1],
        ],
        dtype=np.float64,
    )


def test_cell_classes_separate_target_and_filled_reference_using_one_geometry():
    topology = _Topology(cell_count=2)
    coordinates = np.vstack(
        (
            _cube_vertices(10.0, 11.0, 20.0, 23.0, -5.0, -1.0),
            _cube_vertices(11.0, 12.0, 20.0, 23.0, -5.0, -1.0),
        )
    )
    mesh = SimpleNamespace(
        topology=topology,
        geometry=SimpleNamespace(
            dofmap=np.arange(16, dtype=np.int64).reshape((2, 8)),
            x=coordinates,
        ),
    )
    mesh_data = SimpleNamespace(
        mesh=mesh,
        cell_tags=SimpleNamespace(
            indices=np.asarray([0, 1], dtype=np.int32),
            values=np.asarray([2, 0], dtype=np.int32),
        ),
        rectangular_air_void_audit={"owned_void_box_cell_count": 1},
    )
    cfg = SimpleNamespace(
        tags=SimpleNamespace(air=0, substrate=1, grating=2),
        air_void_box_nm=(11.0, 12.0, 20.0, 23.0, -5.0, -1.0),
    )

    classes = _mesh_cell_classes(mesh_data, cfg)

    assert topology.permutation_creations == 1
    assert len(classes) == 2
    air = next(row for row in classes if row["material_tag"] == cfg.tags.air)
    grating = next(row for row in classes if row["material_tag"] == cfg.tags.grating)
    assert air["target_cell_count"] == 1
    assert air["filled_reference_cell_count"] == 0
    assert air["target_representative_cell"] == 1
    assert air["target_representative_cell_permutation"] == 7
    assert air["target_representative_cell_coordinates_nm"] == coordinates[8:16].tolist()
    assert grating["target_cell_count"] == 1
    assert grating["filled_reference_cell_count"] == 2
    assert grating["target_representative_cell"] == 0
    assert grating["target_representative_cell_permutation"] == 7
    assert grating["models_present"] == ["target", "filled_reference"]
    assert air["metric_identity"] == grating["metric_identity"]
    assert air["representative_bounds_nm"] == [
        [11.0, 12.0],
        [20.0, 23.0],
        [-5.0, -1.0],
    ]
    assert grating["representative_bounds_nm"] == [
        [10.0, 11.0],
        [20.0, 23.0],
        [-5.0, -1.0],
    ]


def test_facet_pair_inventory_keeps_duplicate_facet_ids_and_actual_boundary_adjacency(
    monkeypatch,
):
    centers_by_id = {
        0: [0.0, 0.5, 0.5],
        1: [0.0, 0.5, 0.5],
        2: [1.0, 0.5, 0.5],
        3: [1.0, 0.5, 0.5],
        4: [0.5, 0.0, 0.5],
        5: [0.5, 0.0, 0.5],
        6: [0.5, 1.0, 0.5],
        7: [0.5, 1.0, 0.5],
        8: [0.5, 0.5, 0.0],
        9: [0.5, 0.5, 0.0],
        10: [0.5, 0.5, 1.0],
        11: [0.5, 0.5, 1.0],
    }
    fake_mesh = SimpleNamespace(
        compute_midpoints=lambda _mesh, _dimension, facets: np.asarray(
            [centers_by_id[int(facet)] for facet in facets], dtype=np.float64
        )
    )
    monkeypatch.setitem(sys.modules, "dolfinx", SimpleNamespace(mesh=fake_mesh))

    mesh = SimpleNamespace(
        topology=_Topology(),
        geometry=SimpleNamespace(
            dofmap=np.arange(8, dtype=np.int64).reshape((1, 8)),
            x=_cube_vertices(0.0, 1.0),
        ),
    )
    facet_tags = SimpleNamespace(
        indices=np.arange(12, dtype=np.int32),
        values=np.asarray([1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6], dtype=np.int32),
    )
    mesh_data = SimpleNamespace(
        mesh=mesh,
        facet_tags=facet_tags,
        cell_tags=SimpleNamespace(
            indices=np.asarray([0], dtype=np.int32),
            values=np.asarray([9], dtype=np.int32),
        ),
    )
    cfg = SimpleNamespace(
        tags=SimpleNamespace(
            x_min=1,
            x_max=2,
            y_min=3,
            y_max=4,
            z_min=5,
            z_max=6,
        )
    )

    inventory = _facet_pair_inventory(mesh_data, cfg)

    assert inventory["x_periodic_coordinate_pairing_pass"] is True
    assert inventory["y_periodic_coordinate_pairing_pass"] is True
    assert inventory["top_bottom_port_coordinate_pairing_pass"] is True
    assert inventory["x_periodic_face_pair_count_per_side"] == 2
    assert inventory["facet_tag_counts"] == {str(tag): 2 for tag in range(1, 7)}
    assert inventory["facet_id_pairings"]["x_periodic"] == [
        {
            "projected_center_nm": [0.5, 0.5],
            "minus_or_bottom_facet_id": 0,
            "plus_or_top_facet_id": 2,
        },
        {
            "projected_center_nm": [0.5, 0.5],
            "minus_or_bottom_facet_id": 1,
            "plus_or_top_facet_id": 3,
        },
    ]
    assert [row["facet_id"] for row in inventory["boundary_face_cells"]] == [8, 10]
    assert [row["cell_id"] for row in inventory["boundary_face_cells"]] == [0, 0]
    assert [row["cell_permutation"] for row in inventory["boundary_face_cells"]] == [7, 7]
