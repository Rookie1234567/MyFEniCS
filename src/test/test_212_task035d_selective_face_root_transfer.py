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
from src.adaptivity.selective_face_root_transfer import (
    build_selective_face_root_transfer,
)


_FACE_LEFT = (2, 1, 0, 1, 0, 1)
_FACE_RIGHT = (2, 1, 1, 2, 0, 1)


def _face_points(
    geometry_key: tuple[int, ...],
) -> tuple[tuple[int, int, int], ...]:
    axis, plane, u0, u1, v0, v1 = geometry_key
    assert axis == 2
    return (
        (u0, v0, plane),
        (u1, v0, plane),
        (u0, v1, plane),
        (u1, v1, plane),
    )


def _edge_key(
    left: tuple[int, int, int],
    right: tuple[int, int, int],
) -> tuple[int, ...]:
    return tuple(value for point in sorted((left, right)) for value in point)


def _face_edge_keys(
    geometry_key: tuple[int, ...],
) -> tuple[tuple[int, ...], ...]:
    points = _face_points(geometry_key)
    return tuple(
        _edge_key(points[left], points[right])
        for left, right in ((0, 1), (0, 2), (1, 3), (2, 3))
    )


def _entity(
    dimension: int,
    geometry_key: tuple[int, ...],
    degree: int,
) -> PhysicalTraceEntity:
    count = degree if dimension == 1 else 2 * degree * (degree - 1)
    points = (
        (
            tuple(geometry_key[:3]),
            tuple(geometry_key[3:]),
        )
        if dimension == 1
        else _face_points(geometry_key)
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


def _authority(
    faces: tuple[tuple[int, ...], ...],
    *,
    selected: bool,
) -> BrokenHexTraceConstraintAuthority:
    edge_keys = sorted(
        {
            edge_key
            for face in faces
            for edge_key in _face_edge_keys(face)
        }
    )
    entities = tuple(
        [_entity(1, key, 5) for key in edge_keys]
        + [
            _entity(2, key, 6 if selected else 5)
            for key in sorted(faces)
        ]
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
        selected_p6_face_geometry_keys=tuple(sorted(faces)) if selected else (),
        audit=MappingProxyType({"pass": True}),
    )


def test_selective_face_root_transfer_closes_full_face_primal_dual() -> None:
    transfer = build_selective_face_root_transfer(
        _authority((_FACE_LEFT,), selected=False),
        _authority((_FACE_LEFT,), selected=True),
        auxiliary_rows=3,
    )
    audit = transfer.audit
    assert audit["pass"] is True
    assert audit["schema_version"].endswith(".v2")
    assert audit["trace_dimension_delta"] == 20
    assert audit["reference_face_closure_shape"] == [80, 60]
    assert audit["reference_face_closure_rank"] == 60
    assert audit["reference_face_target_edge_source_max"] > 0.4
    assert transfer.trace_injection.shape == (80, 60)
    assert transfer.total_injection.shape == (83, 63)
    assert transfer.trace_complement.shape == (80, 20)
    assert transfer.face_generator_slices[_FACE_LEFT] == (0, 20)

    rng = np.random.default_rng(20260727)
    coarse = rng.standard_normal(63) + 1j * rng.standard_normal(63)
    enriched = transfer.prolong_primal(coarse)
    assert np.allclose(enriched[:20], coarse[:20])
    assert np.array_equal(enriched[-3:], coarse[-3:])

    edge_only = np.zeros(63, dtype=np.complex128)
    edge_only[:20] = coarse[:20]
    enriched_edge_only = transfer.prolong_primal(edge_only)
    assert np.linalg.norm(enriched_edge_only[20:80]) > 1.0e-2

    dual = rng.standard_normal(83) + 1j * rng.standard_normal(83)
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
    with pytest.raises(
        ValueError,
        match="not in the selective complement",
    ):
        transfer.partition_pairing(
            dual,
            np.ones(83, dtype=np.complex128),
        )


def test_shared_edge_uses_global_complement_and_exact_face_decomposition() -> None:
    faces = (_FACE_LEFT, _FACE_RIGHT)
    coarse_authority = _authority(faces, selected=False)
    enriched_authority = _authority(faces, selected=True)
    transfer = build_selective_face_root_transfer(
        coarse_authority,
        enriched_authority,
        auxiliary_rows=2,
    )
    assert transfer.audit["trace_dimension_delta"] == 40
    assert transfer.trace_complement.shape[1] == 40
    assert transfer.audit["face_generator_rank"] == 40
    assert (
        transfer.audit["face_generator_projector_error_max"]
        <= 2.0e-10
    )

    shared_edge = tuple(
        set(_face_edge_keys(_FACE_LEFT))
        & set(_face_edge_keys(_FACE_RIGHT))
    )
    assert len(shared_edge) == 1
    shared_rows = next(
        entity.rows
        for entity in enriched_authority.entities
        if entity.dimension == 1 and entity.geometry_key == shared_edge[0]
    )
    root_position = {
        row: index
        for index, row in enumerate(enriched_authority.graph.root_rows)
    }
    shared_positions = np.asarray(
        [root_position[row] for row in shared_rows],
        dtype=np.int64,
    )
    left_start, left_stop = transfer.face_generator_slices[_FACE_LEFT]
    right_start, right_stop = transfer.face_generator_slices[_FACE_RIGHT]
    cross_gram = (
        transfer.trace_face_generators[:, left_start:left_stop].conj().T
        @ transfer.trace_face_generators[:, right_start:right_stop]
    ).toarray()
    assert np.linalg.norm(cross_gram) > 1.0e-3

    rng = np.random.default_rng(20260728)
    coefficients = (
        rng.standard_normal(40) + 1j * rng.standard_normal(40)
    )
    primal = np.asarray(transfer.total_complement @ coefficients)
    dual = rng.standard_normal(len(primal)) + 1j * rng.standard_normal(
        len(primal)
    )
    pairings = transfer.partition_pairing(dual, primal)
    assert sum(pairings.values()) == pytest.approx(
        np.vdot(dual, primal),
        rel=2.0e-12,
        abs=2.0e-12,
    )
    assert np.linalg.norm(
        transfer.trace_complement[shared_positions].toarray()
    ) > 1.0e-8


def test_full_closure_is_required_by_galerkin_and_schur_congruence() -> None:
    transfer = build_selective_face_root_transfer(
        _authority((_FACE_LEFT,), selected=False),
        _authority((_FACE_LEFT,), selected=True),
        auxiliary_rows=0,
    )
    injection = transfer.trace_injection.toarray()
    old_entity_block_injection = injection.copy()
    old_entity_block_injection[20:, :20] = 0.0
    rng = np.random.default_rng(20260729)
    raw = (
        rng.standard_normal((80, 80))
        + 1j * rng.standard_normal((80, 80))
    )
    operator_a = raw + raw.conj().T
    operator_b = injection.conj().T @ operator_a @ injection
    true_error = np.max(
        np.abs(
            injection.conj().T @ operator_a @ injection
            - operator_b
        )
    )
    old_error = np.max(
        np.abs(
            old_entity_block_injection.conj().T
            @ operator_a
            @ old_entity_block_injection
            - operator_b
        )
    )
    assert true_error <= 2.0e-10
    assert old_error > 1.0e-2

    interior = 12
    raw_ii = (
        rng.standard_normal((interior, interior))
        + 1j * rng.standard_normal((interior, interior))
    )
    block_ii = raw_ii.conj().T @ raw_ii + 2.0 * np.eye(interior)
    block_ti = (
        rng.standard_normal((80, interior))
        + 1j * rng.standard_normal((80, interior))
    )
    raw_tt = (
        rng.standard_normal((80, 80))
        + 1j * rng.standard_normal((80, 80))
    )
    block_tt = raw_tt + raw_tt.conj().T
    schur_a = (
        block_tt
        - block_ti
        @ np.linalg.solve(block_ii, block_ti.conj().T)
    )
    block_tt_b = injection.conj().T @ block_tt @ injection
    block_ti_b = injection.conj().T @ block_ti
    schur_b = (
        block_tt_b
        - block_ti_b
        @ np.linalg.solve(block_ii, block_ti_b.conj().T)
    )
    np.testing.assert_allclose(
        schur_b,
        injection.conj().T @ schur_a @ injection,
        rtol=2.0e-10,
        atol=2.0e-10,
    )


def test_selective_face_root_transfer_rejects_an_already_enriched_coarse() -> None:
    with pytest.raises(
        ValueError,
        match="coarse authority already contains selected",
    ):
        build_selective_face_root_transfer(
            _authority((_FACE_LEFT,), selected=True),
            _authority((_FACE_LEFT,), selected=True),
            auxiliary_rows=0,
        )
