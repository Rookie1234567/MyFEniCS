from __future__ import annotations

from collections import Counter

from mpi4py import MPI
import numpy as np
import pytest

from src.adaptivity.dyadic_hexa_broken_mesh import (
    build_broken_dyadic_hexa_carrier,
)
from src.adaptivity.dyadic_hexa_refinement import (
    DyadicHexKey,
    build_root_dyadic_hexa_forest,
    refine_balanced_dyadic_hexa_forest,
)
from src.adaptivity.hcurl_broken_trace_graph import (
    build_broken_hexa_entity_degree_arrays,
    build_broken_hexa_trace_constraint_authority,
)
from src.adaptivity.hcurl_broken_cell_trace import (
    build_broken_hexa_cell_trace_constraint_map,
)
from src.adaptivity.variable_p_entity_map import (
    build_variable_p_global_entity_map,
)


def _tensor_boxes(
    nx: int,
    ny: int,
    nz: int,
) -> list[tuple[float, float, float, float, float, float]]:
    return [
        (
            float(i),
            float(j),
            float(k),
            float(i + 1),
            float(j + 1),
            float(k + 1),
        )
        for k in range(nz)
        for j in range(ny)
        for i in range(nx)
    ]


def _multilevel_variable_trace_fixture():
    forest = build_root_dyadic_hexa_forest(
        _tensor_boxes(5, 5, 1),
        [1] * 25,
        periodic_axes=("x", "y"),
    )
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(12, 0, 0, 0, 0)],
        maximum_level=2,
    )
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(12, 1, 0, 0, 0)],
        maximum_level=2,
    )
    carrier = build_broken_dyadic_hexa_carrier(
        forest,
        comm=MPI.COMM_WORLD,
    )
    cell_degrees = {
        cell.box: 4 + cell.key.level for cell in forest.leaves
    }
    authority = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=6,
        phase_x=np.exp(0.2j),
        phase_y=np.exp(-0.3j),
        cell_degree_by_box=cell_degrees,
    )
    return forest, carrier, cell_degrees, authority


def test_multilevel_p4_p5_p6_trace_closes_hanging_and_floquet_rows() -> None:
    forest, carrier, cell_degrees, authority = (
        _multilevel_variable_trace_fixture()
    )
    audit = authority.audit
    degree_audit = audit["variable_trace_degree_audit"]

    assert forest.audit["leaf_level_counts"] == {
        "0": 21,
        "1": 31,
        "2": 8,
    }
    assert Counter(
        (
            forest.leaf_by_key[patch.coarse].key.level,
            forest.leaf_by_key[patch.fine[0]].key.level,
        )
        for patch in forest.hanging_faces
    ) == {(0, 1): 8, (1, 2): 5}
    assert audit["pass"] is True
    assert audit["schema_version"] == (
        "task035e.broken-hexa-variable-trace-authority.v1"
    )
    assert audit["variable_trace_opt_in"] is True
    assert audit["trace_degree_values"] == [4, 5, 6]
    assert Counter(audit["hanging_patch_degrees"]) == {4: 8, 5: 5}
    assert degree_audit["fixed_point_lowering_iterations"] == 2
    assert degree_audit["maximum_adjacent_or_periodic_cell_p_jump"] == 1
    assert degree_audit["periodic_entity_degree_closure"] is True
    assert degree_audit["hanging_entity_degree_closure"] is True
    assert degree_audit["exact_sequence_monotone"] is True
    assert degree_audit[
        "inactive_high_order_trace_rows_globally_numbered"
    ] is False
    assert audit["geometry_canonical_entity_degree_sha256"] == (
        "da521efd18f04cda5eb6158af02b8d186f787785ba34e31eb12f21ab99634493"
    )
    assert set(authority.cell_degree_by_box.values()) == {4, 5, 6}
    assert set(authority.edge_degree_by_geometry_key.values()) == {4, 5, 6}
    assert set(authority.face_degree_by_geometry_key.values()) == {4, 5, 6}

    assert authority.hanging_relations
    assert authority.periodic_relations
    for relation in authority.hanging_relations:
        assert len(
            {
                row.degree
                for row in (*relation.slave_rows, *relation.master_rows)
            }
        ) == 1
    for relation in authority.periodic_relations:
        assert len(
            {
                row.degree
                for row in (*relation.slave_rows, *relation.master_rows)
            }
        ) == 1
    assert authority.graph.audit["pass"] is True
    assert authority.graph.audit[
        "hanging_or_periodic_slave_rows_globally_numbered"
    ] is False

    edge_degrees, face_degrees = build_broken_hexa_entity_degree_arrays(
        forest,
        carrier,
        authority,
    )
    cell_degree_array = np.asarray(
        [
            cell_degrees[
                forest.leaves[int(canonical_leaf)].box
            ]
            for canonical_leaf in carrier.canonical_leaf_by_local_cell
        ],
        dtype=np.int32,
    )
    entity_map = build_variable_p_global_entity_map(
        carrier.mesh,
        edge_degrees=edge_degrees,
        face_degrees=face_degrees,
        cell_degrees=cell_degree_array,
    )
    assert entity_map.active_trace_rows == audit["raw_trace_rows"]
    assert entity_map.audit["inactive_modes_globally_numbered"] is False
    assert entity_map.audit["inactive_p6_trace_rows"] > 0
    assert all(
        max(cell.degree_map.faces) <= cell.degree_map.cell
        for cell in entity_map.owned_cells
    )
    constraints = build_broken_hexa_cell_trace_constraint_map(
        forest,
        carrier,
        entity_map,
        authority,
    )
    assert constraints.audit["pass"] is True
    assert constraints.audit["trace_degree_values"] == [4, 5, 6]
    assert constraints.audit["constraint_kinds"] == [
        "hanging",
        "floquet",
    ]
    assert constraints.audit["variable_trace_opt_in"] is True
    assert constraints.audit["local_variable_trace_implemented"] is True
    assert constraints.audit["selective_trace_action"] == (
        "cell_driven_p4_p5_p6_exact_sequence_trace"
    )
    assert constraints.audit[
        "hanging_or_floquet_slave_rows_globally_numbered"
    ] is False


def test_cell_driven_variable_trace_is_explicit_and_fails_closed() -> None:
    forest = build_root_dyadic_hexa_forest(
        _tensor_boxes(2, 1, 1),
        [1, 1],
        periodic_axes=(),
    )
    carrier = build_broken_dyadic_hexa_carrier(
        forest,
        comm=MPI.COMM_SELF,
    )
    cells = tuple(forest.leaves)

    with pytest.raises(ValueError, match="cover every forest leaf"):
        build_broken_hexa_trace_constraint_authority(
            forest,
            carrier,
            degree=4,
            cell_degree_by_box={cells[0].box: 4},
        )
    with pytest.raises(ValueError, match="p jump exceeds one"):
        build_broken_hexa_trace_constraint_authority(
            forest,
            carrier,
            degree=6,
            cell_degree_by_box={
                cells[0].box: 4,
                cells[1].box: 6,
            },
        )
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_broken_hexa_trace_constraint_authority(
            forest,
            carrier,
            degree=6,
            selected_p6_face_geometry_keys=((0, 0, 0, 0, 0, 0),),
            cell_degree_by_box={
                cells[0].box: 5,
                cells[1].box: 6,
            },
        )
