from __future__ import annotations

from dataclasses import FrozenInstanceError
import cmath

import numpy as np
import pytest

from src.adaptivity.task035e_p7_trace_shadow import (
    P7FloquetTraceRelation,
    P7TraceEntityKey,
    SelectiveP7TraceShadowSpace,
    build_closed_p7_trace_shadow_evidence,
    build_p7_trace_shadow_catalog,
    build_selective_p7_trace_shadow_space,
    close_p7_trace_floquet_orbits,
    condense_selective_p7_trace_shadow_tensor,
    evaluate_selective_p7_trace_shadow_dwr,
)


@pytest.fixture(scope="module")
def face_space() -> SelectiveP7TraceShadowSpace:
    return build_selective_p7_trace_shadow_space((), (0,))


@pytest.fixture(scope="module")
def face_orbit():
    nodes = tuple(P7TraceEntityKey(2, entity) for entity in range(4))
    phase_x = cmath.exp(0.2j)
    phase_y = cmath.exp(-0.3j)
    identity = (0, 1, 2, 3)
    relations = (
        P7FloquetTraceRelation(
            "x", nodes[0], nodes[1], identity, phase_x
        ),
        P7FloquetTraceRelation(
            "y", nodes[0], nodes[2], identity, phase_y
        ),
        P7FloquetTraceRelation(
            "x", nodes[2], nodes[3], identity, phase_x
        ),
        P7FloquetTraceRelation(
            "y", nodes[1], nodes[3], identity, phase_y
        ),
    )
    return close_p7_trace_floquet_orbits((nodes[0],), relations)


@pytest.fixture(scope="module")
def face_numerics(face_space: SelectiveP7TraceShadowSpace):
    dimension = int(face_space.catalog.hcurl_p7_element.dim)
    tensor = np.eye(dimension, dtype=np.complex128)
    rng = np.random.default_rng(35270)
    rhs = (
        rng.standard_normal(dimension)
        + 1j * rng.standard_normal(dimension)
    )
    current = (
        rng.standard_normal(882) + 1j * rng.standard_normal(882)
    )
    gradients = (
        rng.standard_normal((59, dimension))
        + 1j * rng.standard_normal((59, dimension))
    )
    schur = condense_selective_p7_trace_shadow_tensor(
        face_space,
        tensor,
        rhs,
    )
    dwr = evaluate_selective_p7_trace_shadow_dwr(
        face_space,
        tensor,
        rhs,
        current,
        gradients,
    )
    return tensor, rhs, current, gradients, schur, dwr


def test_catalog_covers_complete_edge_face_cell_complements() -> None:
    catalog = build_p7_trace_shadow_catalog()
    audit = catalog.audit
    assert audit["component_pass"] is True
    assert audit["hcurl_p6_dimension"] == 882
    assert audit["hcurl_p7_dimension"] == 1344
    assert audit["hcurl_edge_complement_per_entity"] == 1
    assert audit["hcurl_face_complement_per_entity"] == 24
    assert audit["hcurl_cell_complement"] == 306
    assert audit["hcurl_total_complement"] == 462
    assert audit["h1_p6_dimension"] == 343
    assert audit["h1_p7_dimension"] == 512
    assert audit["h1_edge_complement_per_entity"] == 1
    assert audit["h1_face_complement_per_entity"] == 11
    assert audit["h1_cell_complement"] == 91
    assert audit["h1_total_complement"] == 169
    assert len(catalog.hcurl_blocks) == 19
    assert len(catalog.h1_blocks) == 19
    assert all(
        block.audit["pass"] is True
        and block.audit["globally_numbered"] is False
        and block.audit["selectable_as_production"] is False
        for block in (*catalog.hcurl_blocks, *catalog.h1_blocks)
    )
    assert audit["hcurl_naive_prefix_error_max"] > 1.0
    assert audit["h1_naive_prefix_error_max"] > 0.5
    assert audit["prefix_assumption_used"] is False


def test_face_selection_closes_cell_and_exact_sequence(
    face_space: SelectiveP7TraceShadowSpace,
) -> None:
    assert face_space.requested_edges == ()
    assert face_space.requested_faces == (0,)
    assert face_space.selected_edges == ()
    assert face_space.selected_faces == (0,)
    assert face_space.cell_selected is True
    assert face_space.hcurl_dimension == 882 + 24 + 306
    assert face_space.h1_dimension == 343 + 11 + 91
    assert len(face_space.hcurl_trace_dofs) == 432 + 24
    assert len(face_space.hcurl_interior_dofs) == 450 + 306
    assert face_space.audit["gradient_rank"] == face_space.h1_dimension - 1
    assert face_space.audit["gradient_range_error_max"] < 1.0e-10
    assert face_space.audit["inactive_p7_modes_globally_numbered"] is False
    assert face_space.audit["coverage_status"] == "incomplete"
    assert face_space.audit["p6_saturation_status"] == "unknown"
    assert face_space.audit["p6_saturation_measured_pass"] is False


def test_edge_selection_adds_incident_faces_and_full_selection_is_p7() -> None:
    edge = build_selective_p7_trace_shadow_space((0,), ())
    assert edge.selected_edges == (0,)
    assert edge.selected_faces == (0, 1)
    assert edge.audit["closure_added_faces"] == (0, 1)
    assert edge.hcurl_dimension == 882 + 1 + 2 * 24 + 306
    assert edge.h1_dimension == 343 + 1 + 2 * 11 + 91
    assert edge.audit["gradient_rank"] == edge.h1_dimension - 1
    assert edge.audit["gradient_range_error_max"] < 1.0e-10

    full = build_selective_p7_trace_shadow_space(
        tuple(range(12)),
        tuple(range(6)),
    )
    assert full.hcurl_dimension == 1344
    assert full.h1_dimension == 512
    assert full.audit["gradient_rank"] == 511
    assert full.audit["inactive_p7_modes_globally_numbered"] is False
    assert full.selectable_as_production is False
    assert full.next_production_plan is None


def test_invalid_local_selection_fails_closed() -> None:
    with pytest.raises(ValueError, match="requires an edge or face"):
        build_selective_p7_trace_shadow_space()
    with pytest.raises(ValueError, match=r"\[0, 11\]"):
        build_selective_p7_trace_shadow_space((12,), ())
    with pytest.raises(ValueError, match=r"\[0, 5\]"):
        build_selective_p7_trace_shadow_space((), (6,))


def test_face_floquet_orbit_closes_phase_cycle_without_formal_credit(
    face_orbit,
) -> None:
    assert len(face_orbit.requested) == 1
    assert len(face_orbit.selected) == 4
    assert len(face_orbit.closure_added) == 3
    audit = face_orbit.audit
    assert audit["component_pass"] is True
    assert audit["all_requested_orbits_closed"] is True
    assert audit["maximum_selected_orbit_size"] == 4
    assert audit["hcurl_shadow_rows_before_periodic_elimination"] == 96
    assert audit["hcurl_independent_shadow_rows"] == 24
    assert audit["maximum_floquet_cycle_error"] < 1.0e-12
    assert audit["geometry_binding_status"] == "caller_supplied_unverified"
    assert audit["actual_multilevel_plan_binding_status"] == "unknown"
    assert audit["mpi8_partition_identity_status"] == "unknown"
    assert audit["coverage_status"] == "incomplete"
    assert audit["measured_pass"] is False


def test_edge_reversal_orbit_and_inconsistent_cycle() -> None:
    master = P7TraceEntityKey(1, 10)
    slave = P7TraceEntityKey(1, 11)
    edge = close_p7_trace_floquet_orbits(
        (master,),
        (
            P7FloquetTraceRelation(
                "x",
                master,
                slave,
                (1, 0),
                cmath.exp(0.17j),
            ),
        ),
    )
    assert edge.selected == (master, slave)
    assert edge.audit["hcurl_shadow_rows_before_periodic_elimination"] == 2
    assert edge.audit["hcurl_independent_shadow_rows"] == 1

    nodes = tuple(P7TraceEntityKey(2, entity) for entity in range(4))
    identity = (0, 1, 2, 3)
    phase_x = cmath.exp(0.2j)
    phase_y = cmath.exp(-0.3j)
    inconsistent = (
        P7FloquetTraceRelation(
            "x", nodes[0], nodes[1], identity, phase_x
        ),
        P7FloquetTraceRelation(
            "y", nodes[0], nodes[2], identity, phase_y
        ),
        P7FloquetTraceRelation(
            "x", nodes[2], nodes[3], identity, phase_x
        ),
        P7FloquetTraceRelation(
            "y",
            nodes[1],
            nodes[3],
            identity,
            phase_y * cmath.exp(0.1j),
        ),
    )
    with pytest.raises(RuntimeError, match="cycle audit"):
        close_p7_trace_floquet_orbits((nodes[0],), inconsistent)


def test_local_schur_projection_recovery_and_memory_contract(
    face_numerics,
) -> None:
    tensor, rhs, _current, _gradients, result, _dwr = face_numerics
    expansion = result.space.hcurl_expansion
    expected_active = expansion.conj().T @ tensor @ expansion
    expected_rhs = expansion.conj().T @ rhs
    np.testing.assert_allclose(
        result.active_tensor,
        expected_active,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        result.active_tensor,
        result.active_tensor.conj().T,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    rng = np.random.default_rng(27001)
    trace_values = (
        rng.standard_normal(len(result.space.hcurl_trace_dofs))
        + 1j
        * rng.standard_normal(len(result.space.hcurl_trace_dofs))
    )
    active = result.recover_active_coefficients(trace_values)
    residual = expected_active @ active - expected_rhs
    interior = result.space.hcurl_interior_dofs
    trace = result.space.hcurl_trace_dofs
    assert np.max(np.abs(residual[interior]), initial=0.0) < 3.0e-11
    np.testing.assert_allclose(
        residual[trace],
        result.schur_tensor @ trace_values - result.schur_rhs,
        rtol=4.0e-12,
        atol=4.0e-12,
    )
    assert result.audit["active_local_rows"] == 1212
    assert result.audit["active_trace_rows"] == 456
    assert result.audit["active_cell_interior_rows"] == 756
    assert result.audit["global_p7_matrix_constructed"] is False
    assert result.audit["input_p7_tensor_retained"] is False
    assert result.audit["p6_saturation_measured_pass"] is False
    assert result.audit["active_tensor_bytes"] == 1212**2 * 16


def test_selected_59_goal_dwr_closes_but_cannot_pass_f1(
    face_numerics,
) -> None:
    (
        tensor,
        rhs,
        current,
        gradients,
        _schur,
        result,
    ) = face_numerics
    space = result.space
    complement = space.hcurl_expansion[:, 882:]
    expected_residual = complement.conj().T @ (
        rhs - tensor @ (space.catalog.hcurl_p6_to_p7 @ current)
    )
    np.testing.assert_allclose(
        result.projected_residual,
        expected_residual,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        result.correction,
        expected_residual,
        rtol=3.0e-13,
        atol=3.0e-13,
    )
    np.testing.assert_allclose(
        result.signed_contributions,
        result.direct_goal_deltas,
        rtol=2.0e-12,
        atol=2.0e-12,
    )
    assert result.audit["goal_count"] == 59
    assert result.audit["selected_complement_rows"] == 330
    assert result.audit["selected_face_complement_rows"] == 24
    assert result.audit["selected_cell_complement_rows"] == 306
    assert result.audit["can_satisfy_f1_alone"] is False
    assert result.audit["p6_saturation_status"] == "unknown"
    assert result.audit["p6_saturation_measured_pass"] is False

    with pytest.raises(ValueError, match="exactly 59"):
        evaluate_selective_p7_trace_shadow_dwr(
            space,
            tensor,
            rhs,
            current,
            gradients[:58],
        )


def test_closed_evidence_is_hash_bound_and_explicitly_incomplete(
    face_space: SelectiveP7TraceShadowSpace,
    face_orbit,
    face_numerics,
) -> None:
    _tensor, _rhs, _current, _gradients, schur, dwr = face_numerics
    first = build_closed_p7_trace_shadow_evidence(
        source_sha="a" * 40,
        leaf_identity_sha256="b" * 64,
        space=face_space,
        orbit_closure=face_orbit,
        schur=schur,
        dwr=dwr,
    )
    second = build_closed_p7_trace_shadow_evidence(
        source_sha="a" * 40,
        leaf_identity_sha256="b" * 64,
        space=face_space,
        orbit_closure=face_orbit,
        schur=schur,
        dwr=dwr,
    )
    assert dict(first) == dict(second)
    assert len(first["evidence_sha256"]) == 64
    assert first["component_checks_pass"] is True
    assert first["formal_gate_status"] == "unknown"
    assert first["coverage_status"] == "incomplete"
    assert first["measured_pass"] is False
    assert first["actual_multilevel_plan_binding_status"] == "unknown"
    assert first["mpi8_partition_identity_status"] == "unknown"
    assert first["p6_saturation_status"] == "unknown"
    assert first["p6_saturation_measured_pass"] is False
    assert first["can_satisfy_f1_alone"] is False
    assert first["selectable_as_production"] is False
    assert first["next_production_plan"] is None
    assert first["heavy_pde_run"] is False


def test_arrays_and_contracts_are_immutable(
    face_space: SelectiveP7TraceShadowSpace,
    face_numerics,
) -> None:
    _tensor, _rhs, _current, _gradients, schur, dwr = face_numerics
    with pytest.raises(ValueError):
        face_space.hcurl_expansion[0, 0] = 0.0
    with pytest.raises(TypeError):
        face_space.audit["component_pass"] = False
    with pytest.raises(FrozenInstanceError):
        face_space.shadow_only = False
    with pytest.raises(ValueError):
        schur.schur_tensor[0, 0] = 0.0
    with pytest.raises(ValueError):
        dwr.signed_contributions[0] = 0.0
    assert face_space.production_degrees_unchanged == frozenset({4, 5, 6})
    assert face_space.shadow_only is True
    assert face_space.selectable_as_production is False
    assert face_space.next_production_plan is None
