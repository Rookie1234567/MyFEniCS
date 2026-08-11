from __future__ import annotations

import json

import numpy as np
import pytest

from src.solvers import hcurl_h2b_canonical_orbit as c1
from src.solvers import hcurl_h2b_canonical_congruence as c0


def _cell(seed: int, *, material: str = "epsilon-1") -> dict[str, object]:
    return {
        "class_key_sha256": f"{seed + 1:064x}",
        "constraint_pattern_sha256": f"{seed + 101:064x}",
        "expansion_pattern_sha256": f"{seed + 201:064x}",
        "numeric_matrix_sha256": "9" * 64,
        "orientation_identity": {"edge_signs": (1, -1, 1)},
        "material_identity": {"tag": material, "epsilon": 1.0},
        "operator_identity": {"form": "B0", "scalar": "complex128"},
        "cell_metric_identity": {"widths": (0.5, 0.5, 0.5)},
        "independent_global_rows": (10 + seed, 20 + seed, 30 + seed),
        "csr_offsets": (0, 1, 2, 3),
        "csr_columns": (0, 1, 2),
        "coefficients": (1.0 + 0.0j, 1.0 + 0.0j, 1.0 + 0.0j),
    }


def _tokens(seed: int = 0, *, material: str = "epsilon-1"):
    return c0.build_canonical_row_tokens(
        (10 + seed, 20 + seed, 30 + seed),
        (_cell(seed, material=material),),
        task037_extra_h2b=True,
    )


def test_c1_orbit_rebuilds_transform_with_fixed_width_metadata_rows():
    token_map = {index: _tokens() for index in range(4)}
    audit = c1.build_c1_orbit_audit(
        tuple(range(4)), lambda index: token_map[index], task037_extra_h2b=True
    )
    assert audit.neighborhood_count == 4
    assert audit.representative_count == 1
    assert np.array_equal(audit.transform_sha256, audit.repeat_transform_sha256)
    assert audit.retained_metadata_bytes < c1.C1_METADATA_LIMIT_BYTES
    assert not audit.permutations.flags.writeable
    with pytest.raises(ValueError):
        audit.permutations[0, 0] = 1


def test_c1_patch_probe_and_exact_action_closure_with_three_dense_slots():
    tokens = _tokens()
    transform = c0.build_monomial_transform(tokens, tokens, task037_extra_h2b=True)
    matrix = np.asarray(
        ((3.0 + 0j, 0.2 + 0.1j, 0.0 + 0j),
         (0.2 - 0.1j, 2.0 + 0j, 0.4 + 0.2j),
         (0.0 + 0j, 0.4 - 0.2j, 1.5 + 0j)),
        dtype=np.complex128,
        order="C",
    )
    observed: list[int] = []
    audit = c1.audit_c1_patch(
        matrix,
        matrix.copy(order="C"),
        c1._array_sha256(matrix),
        transform,
        c1.fixed_c1_probes(3),
        embed_member=lambda vector: vector.copy(),
        exact_action=lambda vector: matrix @ vector,
        restrict_member=lambda vector: vector.copy(),
        lifecycle_observer=observed.append,
    )
    assert observed == [3]
    assert audit.hermitian_error == 0.0
    assert np.array_equal(audit.hermitian_row_numerator_squared, np.zeros(3))
    assert audit.congruence_relative_error == 0.0
    assert audit.patch_action_relative_error == 0.0
    assert audit.exact_action_relative_error == 0.0
    assert json.loads(json.dumps(audit.jsonable(), allow_nan=False))["finite"] is True


def test_c1_candidate_limit_stops_before_transform(monkeypatch):
    calls = {"transform": 0}

    def forbidden(*args, **kwargs):
        calls["transform"] += 1
        raise AssertionError("candidate limit must precede T construction")

    monkeypatch.setattr(c1, "build_monomial_transform", forbidden)
    with pytest.raises(c1.C1CandidateOrbitLimit) as caught:
        c1.build_c1_orbit_audit(
            tuple(range(33)),
            lambda index: _tokens(index, material=f"epsilon-{index}"),
            task037_extra_h2b=True,
        )
    assert caught.value.representative_count == 33
    assert caught.value.candidate is not None
    assert calls["transform"] == 0


def test_c1_reused_candidate_rejects_changed_token_loader():
    candidate_tokens = {0: _tokens(), 1: _tokens()}
    candidate = c1.build_c1_candidate_audit(
        (0, 1), lambda index: candidate_tokens[index], task037_extra_h2b=True
    )
    changed_tokens = {0: candidate_tokens[0], 1: _tokens(1, material="epsilon-2")}
    with pytest.raises(c1.C1MetadataNotProven):
        c1.build_c1_orbit_audit(
            (0, 1), lambda index: changed_tokens[index],
            task037_extra_h2b=True, candidate=candidate,
        )


def test_c1_maps_underlying_monomial_failure_to_structured_stop(monkeypatch):
    candidate_tokens = {0: _tokens(), 1: _tokens()}
    candidate = c1.build_c1_candidate_audit(
        (0, 1), lambda index: candidate_tokens[index], task037_extra_h2b=True
    )
    calls = {"count": 0}
    actual = c1.build_monomial_transform

    def fail_on_second(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise c0.MonomialTransformNotProven("synthetic C0 failure")
        return actual(*args, **kwargs)

    monkeypatch.setattr(c1, "build_monomial_transform", fail_on_second)
    with pytest.raises(c1.C1MonomialTransformNotProven):
        c1.build_c1_orbit_audit(
            (0, 1), lambda index: candidate_tokens[index],
            task037_extra_h2b=True, candidate=candidate,
        )
    assert calls["count"] == 2


def test_c1_manifest_roundtrip_retains_repeat_transform(tmp_path):
    audit = c1.build_c1_orbit_audit(
        tuple(range(2)), lambda _index: _tokens(), task037_extra_h2b=True
    )
    path = c1.write_c1_orbit_manifest(
        tmp_path,
        audit,
        c1.fixed_c1_probes(3),
        identity={"scope": "synthetic"},
    )
    manifest, arrays = c1.load_c1_orbit_manifest(path)
    assert manifest["audit"]["neighborhood_count"] == 2
    assert np.array_equal(arrays["transform_sha256"], arrays["repeat_transform_sha256"])
    assert manifest["retained_metadata_bytes"] == c1.c1_retained_metadata_bytes(
        manifest, arrays
    )


def test_c1_orbit_metadata_bytes_exclude_patch_evidence_at_production_shape():
    count = 84
    nloc = 882
    hashes = np.zeros((count, 64), dtype=np.uint8)
    row_hashes = np.zeros((count, nloc, 64), dtype=np.uint8)
    arrays = {
        "neighborhood_ids": np.arange(count, dtype=np.int32),
        "orbit_ids": np.zeros(count, dtype=np.int32),
        "representative_ids": np.zeros(count, dtype=np.int32),
        "metadata_sha256": hashes,
        "provenance_sha256": hashes.copy(),
        "row_token_sha256": row_hashes,
        "row_provenance_sha256": row_hashes.copy(),
        "permutations": np.zeros((count, nloc), dtype=np.int32),
        "phases": np.zeros((count, nloc), dtype=np.complex128),
        "transform_sha256": hashes.copy(),
        "repeat_transform_sha256": hashes.copy(),
        "probes": np.zeros((2, nloc), dtype=np.complex128),
    }
    arrays.update(
        {
            f"patch_evidence_{index}": np.zeros(
                (count, 2, nloc), dtype=np.complex128
            )
            for index in range(8)
        }
    )
    manifest = {"schema": c1.C1_SCHEMA, "retained_metadata_bytes": 0}
    orbit_bytes = c1.c1_retained_metadata_bytes(manifest, arrays)
    assert orbit_bytes <= c1.C1_METADATA_LIMIT_BYTES
    assert sum(int(array.nbytes) for array in arrays.values()) > c1.C1_METADATA_LIMIT_BYTES
    assert orbit_bytes < sum(int(array.nbytes) for array in arrays.values())
