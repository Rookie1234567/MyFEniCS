from __future__ import annotations

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
    build_broken_hexa_trace_constraint_authority,
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


def _single_hanging():
    forest = build_root_dyadic_hexa_forest(
        _tensor_boxes(2, 1, 1),
        [1, 1],
        periodic_axes=(),
    )
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(0, 0, 0, 0, 0)],
    )
    carrier = build_broken_dyadic_hexa_carrier(
        forest,
        comm=MPI.COMM_WORLD,
    )
    return forest, carrier


def _nonhanging_face_key(authority) -> tuple[int, ...]:
    hanging = {
        row.entity_geometry_key
        for relation in authority.hanging_relations
        for row in (*relation.slave_rows, *relation.master_rows)
        if row.entity_dimension == 2
    }
    return next(
        entity.geometry_key
        for entity in authority.entities
        if entity.dimension == 2
        and entity.geometry_key not in hanging
    )


@pytest.mark.parametrize(
    ("degree", "raw_rows", "slave_rows", "independent_rows", "authority_sha"),
    (
        (
            4,
            1272,
            144,
            1128,
            "d65bc72969f7ee2180d08563bc75f4c60067a954a518da0b14afed2750ba2177",
        ),
        (
            5,
            2010,
            220,
            1790,
            "47bf22902d63a3428a3d1ebdcab1bfcbb5bd2fd55ee932b5c4351b76592e982d",
        ),
        (
            6,
            2916,
            312,
            2604,
            "b0f12be62cf5c7947d5e682599491b869029a9efff8d0caccf53fcacf1c8aa9e",
        ),
    ),
)
def test_actual_p4_p5_p6_hanging_relations_use_physical_rows(
    degree: int,
    raw_rows: int,
    slave_rows: int,
    independent_rows: int,
    authority_sha: str,
) -> None:
    forest, carrier = _single_hanging()
    authority = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=degree,
    )
    audit = authority.audit
    assert audit["pass"] is True
    assert audit["hanging_patch_count"] == 1
    assert audit["hanging_primary_relation_count"] == 1
    assert audit["hanging_secondary_relation_count"] == 0
    assert audit["raw_trace_rows"] == raw_rows
    assert audit["hanging_slave_rows"] == slave_rows
    assert audit["independent_trace_rows"] == independent_rows
    assert audit["maximum_chain_depth"] == 1
    assert audit["maximum_relation_residual"] == 0.0
    assert audit["physical_authority_sha256"] == authority_sha
    assert len(set(authority.graph.raw_rows)) == raw_rows
    assert all(
        relation.primary for relation in authority.hanging_relations
    )


def test_periodic_corner_hanging_graph_flattens_secondary_equations() -> None:
    boxes = _tensor_boxes(3, 3, 1)
    forest = build_root_dyadic_hexa_forest(
        boxes,
        [1] * len(boxes),
        periodic_axes=("x", "y"),
    )
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(0, 0, 0, 0, 0)],
    )
    carrier = build_broken_dyadic_hexa_carrier(
        forest,
        comm=MPI.COMM_WORLD,
    )
    authority = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=4,
        phase_x=np.exp(0.2j),
        phase_y=np.exp(-0.3j),
    )
    audit = authority.audit
    assert audit["pass"] is True
    assert audit["hanging_patch_count"] == 8
    assert audit["hanging_primary_relation_count"] == 8
    assert audit["hanging_secondary_relation_count"] == 4
    assert audit["periodic_primary_relation_count"] == 64
    assert audit["periodic_secondary_relation_count"] == 8
    assert audit["raw_trace_rows"] == 5120
    assert audit["hanging_slave_rows"] == 1120
    assert audit["independent_trace_rows"] == 3384
    assert audit["maximum_chain_depth"] == 2
    assert audit["periodic_cycle_error"] <= 5.0e-11
    assert audit["maximum_relation_residual"] <= 5.0e-11
    assert audit["physical_authority_sha256"] == (
        "19e032d3b15828dda119a0eef7e5c25b575ea94a0324e30df79b7e35c096afa8"
    )
    assert authority.graph.audit["expansion_storage"] == "csr"
    hashes = MPI.COMM_WORLD.allgather(
        audit["physical_authority_sha256"]
    )
    assert len(set(hashes)) == 1


def test_unmirrored_periodic_refinement_fails_closed() -> None:
    boxes = _tensor_boxes(3, 3, 1)
    forest = build_root_dyadic_hexa_forest(
        boxes,
        [1] * len(boxes),
        periodic_axes=(),
    )
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(0, 0, 0, 0, 0)],
    )
    carrier = build_broken_dyadic_hexa_carrier(
        forest,
        comm=MPI.COMM_SELF,
    )
    with pytest.raises(RuntimeError, match="no translated master"):
        build_broken_hexa_trace_constraint_authority(
            forest,
            carrier,
            degree=4,
            periodic_axes=("x", "y"),
            phase_x=np.exp(0.2j),
            phase_y=np.exp(-0.3j),
        )


def test_one_nonhanging_whole_face_can_recover_p6_rows() -> None:
    forest, carrier = _single_hanging()
    base = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=5,
    )
    selected = _nonhanging_face_key(base)
    enriched = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=5,
        selected_p6_face_geometry_keys=(selected,),
    )

    assert enriched.audit["pass"] is True
    assert enriched.audit["trace_degree_values"] == [5, 6]
    assert enriched.audit["selected_p6_face_count"] == 1
    assert enriched.audit["selective_trace_full3d_dof_delta"] == 20
    assert enriched.audit["raw_trace_rows"] == (
        base.audit["raw_trace_rows"] + 20
    )
    assert enriched.audit["independent_trace_rows"] == (
        base.audit["independent_trace_rows"] + 20
    )
    selected_entity = next(
        entity
        for entity in enriched.entities
        if entity.dimension == 2
        and entity.geometry_key == selected
    )
    assert selected_entity.degree == 6
    assert len(selected_entity.rows) == 60
    assert all(
        entity.degree == 5
        for entity in enriched.entities
        if entity.dimension == 1
    )
    assert enriched.audit["physical_authority_sha256"] != (
        base.audit["physical_authority_sha256"]
    )


def test_selective_p6_face_rejects_hanging_participant() -> None:
    forest, carrier = _single_hanging()
    base = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=5,
    )
    hanging = next(
        row.entity_geometry_key
        for relation in base.hanging_relations
        for row in (*relation.slave_rows, *relation.master_rows)
        if row.entity_dimension == 2
    )
    with pytest.raises(ValueError, match="hanging participant"):
        build_broken_hexa_trace_constraint_authority(
            forest,
            carrier,
            degree=5,
            selected_p6_face_geometry_keys=(hanging,),
        )


def test_selective_p6_face_requires_complete_periodic_orbit() -> None:
    forest = build_root_dyadic_hexa_forest(
        _tensor_boxes(3, 1, 1),
        [1, 1, 1],
        periodic_axes=("x",),
    )
    carrier = build_broken_dyadic_hexa_carrier(
        forest,
        comm=MPI.COMM_WORLD,
    )
    base = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=5,
        phase_x=np.exp(0.2j),
    )
    face_relation = next(
        relation
        for relation in base.periodic_relations
        if relation.slave_rows[0].entity_dimension == 2
    )
    master = face_relation.master_rows[0].entity_geometry_key
    slave = face_relation.slave_rows[0].entity_geometry_key
    with pytest.raises(ValueError, match="complete periodic orbit"):
        build_broken_hexa_trace_constraint_authority(
            forest,
            carrier,
            degree=5,
            phase_x=np.exp(0.2j),
            selected_p6_face_geometry_keys=(slave,),
        )

    enriched = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=5,
        phase_x=np.exp(0.2j),
        selected_p6_face_geometry_keys=(master, slave),
    )
    assert enriched.audit["selected_p6_face_count"] == 2
    assert enriched.audit["selective_trace_full3d_dof_delta"] == 40
    assert enriched.audit["raw_trace_rows"] == (
        base.audit["raw_trace_rows"] + 40
    )
    assert enriched.audit["independent_trace_rows"] == (
        base.audit["independent_trace_rows"] + 20
    )
