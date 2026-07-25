"""Qualification tests for the physical p5-to-p6 H(curl) trace shell."""

from __future__ import annotations

import numpy as np
import pytest

from src.adaptivity.p6_trace_complement_qualification import (
    qualify_p5_p6_nedelec_hexahedron_trace_complement,
)
from src.adaptivity.selective_p6_trace_orbits import (
    validate_missing_trace_intertwining,
)


@pytest.fixture(scope="module")
def qualification():
    return qualify_p5_p6_nedelec_hexahedron_trace_complement()


def test_missing_shell_dimensions_and_hashes_are_explicit(
    qualification,
) -> None:
    assert qualification.audit["pass"] is True
    assert qualification.audit["p5_dimension"] == 540
    assert qualification.audit["p6_dimension"] == 882
    assert qualification.edge.retained_dimension == 5
    assert qualification.edge.enriched_dimension == 6
    assert qualification.edge.missing_dimension == 1
    assert qualification.face.retained_dimension == 40
    assert qualification.face.enriched_dimension == 60
    assert qualification.face.missing_dimension == 20
    assert len(qualification.qualification_sha256) == 64
    assert len(qualification.edge.shell_sha256) == 64
    assert len(qualification.face.shell_sha256) == 64
    assert qualification.edge.shell_sha256 != qualification.face.shell_sha256


@pytest.mark.parametrize("entity_kind", ["edge", "face"])
def test_riesz_projection_rank_condition_and_leakage(
    qualification,
    entity_kind: str,
) -> None:
    shell = getattr(qualification, entity_kind)
    retained = shell.retained_embedding
    gram = shell.trace_l2_gram
    missing = shell.missing_basis
    projector = shell.retained_riesz_projector

    assert np.linalg.matrix_rank(retained) == shell.retained_dimension
    assert np.linalg.matrix_rank(gram) == shell.enriched_dimension
    assert (
        np.linalg.matrix_rank(np.concatenate((retained, missing), axis=1))
        == shell.enriched_dimension
    )
    np.testing.assert_allclose(
        missing.T @ gram @ missing,
        np.eye(shell.missing_dimension),
        atol=2.0e-10,
        rtol=2.0e-10,
    )
    np.testing.assert_allclose(
        retained.T @ gram @ missing,
        0.0,
        atol=2.0e-10,
        rtol=0.0,
    )
    np.testing.assert_allclose(
        projector @ projector,
        projector,
        atol=2.0e-10,
        rtol=2.0e-10,
    )
    np.testing.assert_allclose(
        projector.T @ gram,
        gram @ projector,
        atol=2.0e-10,
        rtol=2.0e-10,
    )
    assert shell.audit["direct_sum_condition_number"] < 1.0e8
    assert all(shell.audit["checks"].values())


@pytest.mark.parametrize("entity_kind", ["edge", "face"])
def test_entity_transformations_intertwine_both_shells(
    qualification,
    entity_kind: str,
) -> None:
    shell = getattr(qualification, entity_kind)
    for generator in shell.transformation_generators:
        enriched = generator.enriched_transform
        retained_transform = generator.retained_transform
        missing_transform = generator.induced_missing_transform
        np.testing.assert_allclose(
            enriched @ shell.retained_embedding,
            shell.retained_embedding @ retained_transform,
            atol=2.0e-10,
            rtol=2.0e-10,
        )
        np.testing.assert_allclose(
            enriched @ shell.missing_basis,
            shell.missing_basis @ missing_transform,
            atol=2.0e-10,
            rtol=2.0e-10,
        )
        np.testing.assert_allclose(
            enriched.T @ shell.trace_l2_gram @ enriched,
            shell.trace_l2_gram,
            atol=2.0e-10,
            rtol=2.0e-10,
        )
        assert generator.audit["pass"] is True
        assert all(generator.audit["checks"].values())


def test_qualified_basis_is_direct_input_to_periodic_orbit_validator(
    qualification,
) -> None:
    for shell in (qualification.edge, qualification.face):
        for generator in shell.transformation_generators:
            projection = validate_missing_trace_intertwining(
                enriched_transform=generator.enriched_transform,
                retained_transform=generator.retained_transform,
                retained_embedding=shell.retained_embedding,
                missing_embedding=shell.missing_basis,
                expected_missing_transform=(
                    generator.induced_missing_transform
                ),
                tolerance=2.0e-10,
            )
            assert projection.audit["pass"] is True
            assert (
                projection.missing_dimension == shell.missing_dimension
            )


def test_covariant_piola_and_all_reference_entities_are_qualified(
    qualification,
) -> None:
    for shell in (qualification.edge, qualification.face):
        piola = shell.audit["piola"]
        assert (
            piola["push_forward_matches_explicit_covariant_piola"]
            <= 2.0e-10
        )
        assert piola["push_pull_roundtrip_relative_error"] <= 2.0e-10
        assert (
            piola["tangential_covector_pullback_relative_error"]
            <= 2.0e-10
        )
        assert shell.audit["all_entity_gram_max_relative_error"] <= 2.0e-10
        assert (
            shell.audit["all_entity_embedding_max_relative_error"]
            <= 2.0e-10
        )


def test_qualification_cannot_number_inactive_modes(
    qualification,
) -> None:
    assert qualification.audit["global_rows_allocated"] == 0
    assert (
        qualification.audit["inactive_modes_allocated_global_rows"] is False
    )
    for shell in (qualification.edge, qualification.face):
        assert shell.audit["global_rows_allocated"] == 0
        assert all(mode.global_row is None for mode in shell.mode_metadata)
        assert len(
            {mode.coefficient_sha256 for mode in shell.mode_metadata}
        ) == shell.missing_dimension


def test_fail_closed_thresholds_reject_unqualified_construction() -> None:
    with pytest.raises(ValueError, match="at least seven"):
        qualify_p5_p6_nedelec_hexahedron_trace_complement(
            quadrature_points_per_axis=6
        )
    with pytest.raises(RuntimeError, match="well_conditioned"):
        qualify_p5_p6_nedelec_hexahedron_trace_complement(
            condition_limit=10.0
        )


def test_scope_does_not_claim_mesh_matrix_or_dwr_integration(
    qualification,
) -> None:
    for audit in (
        qualification.audit,
        qualification.edge.audit,
        qualification.face.audit,
    ):
        assert audit["matrix_assembly_performed"] is False
        assert audit["dolfinx_mesh_integration_performed"] is False
        assert audit["periodic_orbit_selection_performed"] is False
        assert audit["actual_channel_dwr_computed"] is False
