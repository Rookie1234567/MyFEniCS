from __future__ import annotations

import json

import numpy as np
import pytest

from benchmarks.task035d_selective_face_complement import main
from src.adaptivity.selective_face_complement import (
    build_selective_p6_face_reference_catalog,
    build_selective_p6_face_reference_complement,
)


def test_one_face_is_true_nested_exact_sequence_complement() -> None:
    result = build_selective_p6_face_reference_complement(0)
    assert result.audit["pass"] is True
    assert result.hcurl.injection.shape == (770, 750)
    assert result.hcurl.complement.shape == (770, 20)
    assert result.h1.injection.shape == (286, 277)
    assert result.h1.complement.shape == (286, 9)
    assert result.face_interior.p5_to_p6.shape == (60, 40)
    assert result.face_interior.complement_to_p6.shape == (60, 20)
    assert result.face_interior.p6_tangential_riesz_gram.shape == (60, 60)
    assert result.face_interior.audit["pass"] is True
    assert (
        result.face_interior.audit[
            "maximum_d4_embedding_commuting_error"
        ]
        <= 5.0e-11
    )
    assert (
        result.face_interior.audit[
            "maximum_d4_complement_closure_error"
        ]
        <= 5.0e-11
    )
    assert (
        result.audit["gradient_injection_commuting_error_max"]
        <= 5.0e-11
    )
    assert result.audit["hcurl_d4_orientation"]["pass"] is True
    assert result.audit["h1_d4_orientation"]["pass"] is True
    assert result.audit["heavy_pde_authorized"] is False
    assert result.audit["full_p6_matrix_constructed"] is False

    coarse = result.coarse_space.hcurl_to_p6
    enriched = result.enriched_space.hcurl_to_p6
    np.testing.assert_allclose(
        enriched @ result.hcurl.injection,
        coarse,
        rtol=5.0e-11,
        atol=5.0e-11,
    )
    coarse_closure = np.asarray(
        result.coarse_space.hcurl_element.entity_closure_dofs[2][0],
        dtype=np.int64,
    )
    enriched_closure = np.asarray(
        result.enriched_space.hcurl_element.entity_closure_dofs[2][0],
        dtype=np.int64,
    )
    closure_injection = result.hcurl.injection[
        np.ix_(enriched_closure, coarse_closure)
    ]
    assert closure_injection.shape == (80, 60)
    assert np.linalg.matrix_rank(closure_injection) == 60
    np.testing.assert_allclose(
        closure_injection[:20, :20],
        np.eye(20),
        rtol=5.0e-11,
        atol=5.0e-11,
    )
    assert np.max(np.abs(closure_injection[20:, :20])) > 0.4
    np.testing.assert_allclose(
        closure_injection[20:, 20:],
        result.face_interior.p5_to_p6,
        rtol=5.0e-11,
        atol=5.0e-11,
    )
    outside_coarse = np.setdiff1d(
        np.arange(result.hcurl.injection.shape[1]),
        coarse_closure,
    )
    outside_enriched = np.setdiff1d(
        np.arange(result.hcurl.injection.shape[0]),
        enriched_closure,
    )
    assert np.max(
        np.abs(
            result.hcurl.injection[
                np.ix_(enriched_closure, outside_coarse)
            ]
        )
    ) <= 5.0e-11
    assert np.max(
        np.abs(
            result.hcurl.injection[
                np.ix_(outside_enriched, coarse_closure)
            ]
        )
    ) <= 5.0e-11


def test_catalog_covers_all_faces_and_is_deterministic() -> None:
    first = build_selective_p6_face_reference_catalog()
    second = build_selective_p6_face_reference_catalog()
    assert first == second
    assert first["pass"] is True
    assert first["qualified_local_faces"] == 6
    assert len(first["entries"]) == 6
    assert {entry["local_face"] for entry in first["entries"]} == set(
        range(6)
    )
    assert all(
        entry["non_hanging_physical_face_only"] is True
        and entry["periodic_orbit_closure_required"] is True
        and entry["dtn_port_complement_qualified"] is False
        for entry in first["entries"]
    )
    canonical = None
    for local_face in range(6):
        result = build_selective_p6_face_reference_complement(local_face)
        coarse_closure = np.asarray(
            result.coarse_space.hcurl_element.entity_closure_dofs[2][
                local_face
            ],
            dtype=np.int64,
        )
        enriched_closure = np.asarray(
            result.enriched_space.hcurl_element.entity_closure_dofs[2][
                local_face
            ],
            dtype=np.int64,
        )
        closure = result.hcurl.injection[
            np.ix_(enriched_closure, coarse_closure)
        ]
        assert closure.shape == (80, 60)
        assert np.linalg.matrix_rank(closure) == 60
        if canonical is None:
            canonical = closure
        else:
            np.testing.assert_allclose(
                closure,
                canonical,
                rtol=5.0e-11,
                atol=5.0e-11,
            )


@pytest.mark.parametrize("local_face", (-1, 6))
def test_invalid_face_fails_closed(local_face: int) -> None:
    with pytest.raises(ValueError, match=r"\[0, 5\]"):
        build_selective_p6_face_reference_complement(local_face)


def test_serial_runner_persists_hash_bound_preflight(
    tmp_path,
) -> None:
    output = tmp_path / "authority.json"
    source_sha = "a" * 40
    assert (
        main(
            [
                "--source-sha",
                source_sha,
                "--output",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pass"] is True
    assert payload["source_sha"] == source_sha
    assert payload["mpi_size"] == 1
    assert payload["mpi_partition_independent"] is True
    assert payload["scope"]["heavy_pde_started"] is False
    assert payload["scope"]["heavy_pde_authorized"] is False

    with pytest.raises(ValueError, match="source SHA"):
        main(
            [
                "--source-sha",
                "not-a-sha",
                "--output",
                str(tmp_path / "bad.json"),
            ]
        )
