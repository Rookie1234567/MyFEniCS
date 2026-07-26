from __future__ import annotations

from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI
import pytest

from src.adaptivity.dyadic_hexa_broken_mesh import (
    build_broken_dyadic_hexa_carrier,
)
from src.adaptivity.dyadic_hexa_refinement import (
    DyadicHexKey,
    build_root_dyadic_hexa_forest,
    refine_balanced_dyadic_hexa_forest,
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


def _single_hanging_forest():
    forest = build_root_dyadic_hexa_forest(
        _tensor_boxes(2, 1, 1),
        [1, 1],
        periodic_axes=(),
    )
    return refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(0, 0, 0, 0, 0)],
    )


def test_actual_broken_hexa_carrier_classifies_only_hanging_crack() -> None:
    carrier = build_broken_dyadic_hexa_carrier(
        _single_hanging_forest(),
        comm=MPI.COMM_WORLD,
    )
    audit = carrier.audit
    assert audit["pass"] is True
    assert audit["canonical_leaf_count"] == 9
    assert audit["canonical_vertex_count"] == 31
    assert audit["carrier_global_topological_facet_count"] == 42
    assert audit["topological_exterior_facet_count"] == 30
    assert audit["physical_exterior_facet_count"] == 25
    assert audit["artificial_hanging_exterior_facet_count"] == 5
    assert audit["physical_boundary_area"] == pytest.approx(10.0)
    assert audit["leaf_catalog_sha256"] == (
        "703850c6f451146cedc9940d29932947e767f665646202bb4ce75e9aa50aaeb3"
    )
    assert audit["canonical_connectivity_sha256"] == (
        "7dba211efb1e14ba378bbf1d79ca9bfc3f0cb8f117b53b67010c50ec4ba74070"
    )
    assert audit["physical_facet_catalog_sha256"] == (
        "e2b15475f41f3af8f491cbe763e025b63559bb32273a94151cf24caf01b1c20b"
    )
    assert audit["artificial_facet_catalog_sha256"] == (
        "730be19df96988a0651cb9413e8c165dfb6ba63f1d3b72e8836de82f395688db"
    )
    assert len(carrier.physical_boundary_tags.indices) < audit[
        "topological_exterior_facet_count"
    ]

    space = fem.functionspace(
        carrier.mesh,
        element(
            "N1curl",
            "hexahedron",
            4,
            dtype=default_real_type,
        ),
    )
    assert int(space.element.basix_element.dim) == 300
    assert int(space.dofmap.index_map.size_global) == 2244
    if MPI.COMM_WORLD.size == 2:
        assert audit["cross_rank_hanging_patch_count"] == 0


def test_material_protection_makes_material_interface_conforming() -> None:
    forest = build_root_dyadic_hexa_forest(
        _tensor_boxes(2, 1, 1),
        [11, 22],
        periodic_axes=(),
        protect_material_interfaces=True,
    )
    refined = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(0, 0, 0, 0, 0)],
    )
    carrier = build_broken_dyadic_hexa_carrier(
        refined,
        comm=MPI.COMM_WORLD,
    )
    assert len(refined.leaves) == 16
    assert carrier.audit["hanging_patch_count"] == 0
    assert carrier.audit["artificial_hanging_exterior_facet_count"] == 0
    local_counts = {
        tag: int((carrier.cell_tags.values == tag).sum())
        for tag in (11, 22)
    }
    global_counts = {
        tag: MPI.COMM_WORLD.allreduce(count, op=MPI.SUM)
        for tag, count in local_counts.items()
    }
    assert global_counts == {11: 8, 22: 8}


def test_xy_periodic_corner_refinement_has_complete_carrier_catalog() -> None:
    boxes = _tensor_boxes(3, 3, 1)
    forest = build_root_dyadic_hexa_forest(
        boxes,
        [1] * len(boxes),
        periodic_axes=("x", "y"),
    )
    refined = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(0, 0, 0, 0, 0)],
    )
    carrier = build_broken_dyadic_hexa_carrier(
        refined,
        comm=MPI.COMM_WORLD,
    )
    assert carrier.audit["pass"] is True
    assert carrier.audit["canonical_leaf_count"] == 37
    assert carrier.audit["artificial_hanging_exterior_facet_count"] == (
        5 * carrier.audit["hanging_patch_count"]
    )
    if MPI.COMM_WORLD.size == 2:
        assert carrier.audit["cross_rank_hanging_patch_count"] == 2
    for axis in ("x", "y"):
        assert refined.audit["periodic_boundary_audit"][axis]["matching"] is True


def test_unexplained_internal_void_fails_closed() -> None:
    forest = build_root_dyadic_hexa_forest(
        [
            (0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
            (2.0, 0.0, 0.0, 3.0, 1.0, 1.0),
        ],
        [1, 1],
        periodic_axes=(),
    )
    with pytest.raises(RuntimeError, match="not explained"):
        build_broken_dyadic_hexa_carrier(
            forest,
            comm=MPI.COMM_SELF,
        )
