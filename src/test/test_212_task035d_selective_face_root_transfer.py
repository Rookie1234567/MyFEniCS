from __future__ import annotations

from types import MappingProxyType

import numpy as np
import pytest

from src.adaptivity.hcurl_broken_trace_graph import (
    BrokenHexTraceConstraintAuthority,
    PhysicalTraceEntity,
)
from src.adaptivity.hcurl_trace_constraint_graph import (
    PhysicalTraceRowKey,
    compose_and_flatten_trace_constraints,
)
from src.adaptivity.selective_face_complement import (
    build_selective_p6_face_reference_complement,
)
from src.adaptivity.selective_face_root_transfer import (
    build_selective_face_root_transfer,
)


_EDGE_KEY = (0, 0, 0, 1, 0, 0)
_FACE_KEY = (2, 1, 0, 1, 0, 1)


def _entity(
    dimension: int,
    geometry_key: tuple[int, ...],
    degree: int,
) -> PhysicalTraceEntity:
    count = degree if dimension == 1 else 2 * degree * (degree - 1)
    points = (
        ((0, 0, 0), (1, 0, 0))
        if dimension == 1
        else (
            (0, 0, 1),
            (0, 1, 1),
            (1, 0, 1),
            (1, 1, 1),
        )
    )
    return PhysicalTraceEntity(
        dimension=dimension,
        geometry_key=geometry_key,
        degree=degree,
        canonical_points=points,
        rows=tuple(
            PhysicalTraceRowKey(
                entity_dimension=dimension,
                entity_geometry_key=geometry_key,
                degree=degree,
                mode=mode,
            )
            for mode in range(count)
        ),
    )


def _authority(*, selected: bool) -> BrokenHexTraceConstraintAuthority:
    entities = (
        _entity(1, _EDGE_KEY, 5),
        _entity(2, _FACE_KEY, 6 if selected else 5),
    )
    graph = compose_and_flatten_trace_constraints(
        tuple(row for entity in entities for row in entity.rows),
        (),
    )
    return BrokenHexTraceConstraintAuthority(
        degree=5,
        entities=entities,
        hanging_relations=(),
        periodic_relations=(),
        graph=graph,
        selected_p6_face_geometry_keys=(_FACE_KEY,) if selected else (),
        audit=MappingProxyType({"pass": True}),
    )


def test_selective_face_root_transfer_closes_primal_dual_and_complement() -> None:
    transfer = build_selective_face_root_transfer(
        _authority(selected=False),
        _authority(selected=True),
        auxiliary_rows=3,
    )
    audit = transfer.audit
    assert audit["pass"] is True
    assert audit["trace_dimension_delta"] == 20
    assert transfer.trace_injection.shape == (65, 45)
    assert transfer.total_injection.shape == (68, 48)
    assert transfer.trace_complement.shape == (65, 20)
    assert transfer.complement_slices[_FACE_KEY] == (0, 20)

    rng = np.random.default_rng(20260727)
    coarse = rng.standard_normal(48) + 1j * rng.standard_normal(48)
    enriched = transfer.prolong_primal(coarse)
    reference = build_selective_p6_face_reference_complement(0)
    assert np.allclose(enriched[:5], coarse[:5])
    assert np.allclose(
        enriched[5:65],
        reference.face_interior.p5_to_p6 @ coarse[5:45],
    )
    assert np.array_equal(enriched[-3:], coarse[-3:])

    dual = rng.standard_normal(68) + 1j * rng.standard_normal(68)
    left = np.vdot(enriched, dual)
    right = np.vdot(coarse, transfer.restrict_dual(dual))
    assert left == pytest.approx(right, rel=1.0e-12, abs=1.0e-12)
    complement = transfer.total_complement.toarray()
    assert np.max(
        np.abs(transfer.total_injection.conj().T @ complement)
    ) <= 2.0e-10
    assert np.allclose(
        complement.conj().T @ complement,
        np.eye(20),
        rtol=2.0e-10,
        atol=2.0e-10,
    )


def test_selective_face_root_transfer_rejects_an_already_enriched_coarse() -> None:
    with pytest.raises(
        ValueError,
        match="coarse authority already contains selected",
    ):
        build_selective_face_root_transfer(
            _authority(selected=True),
            _authority(selected=True),
            auxiliary_rows=0,
        )
