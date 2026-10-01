"""Task40 first-direction comparison in FE and physical port norms."""

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks.check_task40_first_arnoldi_hp_gate_v1 import check_saved_pair
from src.runners.physical_retained_outer_adapter import (
    _first_direction_pair_hp_comparison,
)


_MODE_SHA = "a" * 64


def _carrier(normalization_h, *, mode_sha=_MODE_SHA, identity_h=None):
    normalization_h = tuple(float(value) for value in normalization_h)
    if identity_h is None:
        identity_h = normalization_h
    entries = tuple(
        SimpleNamespace(
            normalization_h=h,
            mode_identity={
                "mode_index": index,
                "projection_denominator": float(identity_h[index]),
            },
        )
        for index, h in enumerate(normalization_h)
    )
    return SimpleNamespace(
        entries=entries,
        mode_manifest_sha256=mode_sha,
    )


def _compare(reference, candidate, carrier, *, expected_mode_sha=_MODE_SHA):
    return _first_direction_pair_hp_comparison(
        reference,
        candidate,
        active_rows=2,
        carrier=carrier,
        expected_mode_manifest_sha256=expected_mode_sha,
    )


def _manifest_hash(manifest):
    payload = json.dumps(
        manifest,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def test_hp_metric_is_invariant_under_port_basis_rescaling():
    h = np.asarray([0.25, 4.0], dtype=np.float64)
    reference = np.asarray(
        [1.0 + 0.5j, -0.25j, 0.5 + 0.75j, -1.0j],
        dtype=np.complex128,
    )
    candidate = reference.copy()
    candidate[:2] += [2.0e-13 - 1.0e-13j, -3.0e-13j]
    candidate[2:] += [2.0e-3 + 4.0e-3j, -3.0e-3j]

    original = _compare(reference, candidate, _carrier(h))

    basis_scale = np.asarray(
        [1.0e-4 * np.exp(0.7j), 1.0e4 * np.exp(-0.4j)],
        dtype=np.complex128,
    )
    rescaled_h = h * np.abs(basis_scale) ** 2
    rescaled_reference = reference.copy()
    rescaled_candidate = candidate.copy()
    rescaled_reference[2:] /= basis_scale
    rescaled_candidate[2:] /= basis_scale
    rescaled = _compare(
        rescaled_reference,
        rescaled_candidate,
        _carrier(rescaled_h),
    )

    assert rescaled["fixed_basis_trace_coefficient_relative"] == pytest.approx(
        original["fixed_basis_trace_coefficient_relative"], rel=1e-12
    )
    assert rescaled["port_modal_gram_relative"] == pytest.approx(
        original["port_modal_gram_relative"], rel=1e-12
    )
    assert rescaled["joint_mixed_metric_relative_diagnostic"] == pytest.approx(
        original["joint_mixed_metric_relative_diagnostic"], rel=1e-12
    )


def test_physical_port_perturbation_still_fails_the_strict_gate():
    reference = np.asarray([1.0, -0.5j, 2.0 + 1.0j, -0.25j])
    candidate = reference.copy()
    candidate[-1] += 1.0e-4

    result = _compare(reference, candidate, _carrier([0.25, 4.0]))

    assert result["fixed_basis_trace_coefficient_relative"] == 0.0
    assert result["port_modal_gram_relative"] > result["limit"]
    assert not result["passed"]


def test_h_value_must_match_mode_identity():
    with pytest.raises(ValueError, match="H does not match"):
        _compare(
            np.asarray([1.0, 2.0, 1.0, 1.0]),
            np.asarray([1.0, 2.0, 1.0, 1.0]),
            _carrier([2.0, 3.0], identity_h=[2.0, 3.5]),
        )


def test_mode_manifest_identity_must_match_the_active_adapter():
    with pytest.raises(ValueError, match="manifest identity mismatch"):
        _compare(
            np.asarray([1.0, 2.0, 1.0, 1.0]),
            np.asarray([1.0, 2.0, 1.0, 1.0]),
            _carrier([2.0, 3.0], mode_sha="b" * 64),
        )


def _write_saved_checker_case(tmp_path, *, perturb_port=False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "fullspace-dtn.mode-manifest.v1",
        "profile": "test",
        "mode_count": 2,
        "modes": [
            {
                "schema": "fullspace-dtn.mode.v1",
                "mode_index": index,
                "side": "top",
                "m": 0,
                "n": 0,
                "polarization": polarization,
                "alpha": {"real": 0.0, "imag": 0.0},
                "gamma": {"real": 0.0, "imag": 0.0},
                "k_vector": [
                    {"real": 0.0, "imag": 0.0},
                    {"real": 0.0, "imag": 0.0},
                    {"real": 1.0, "imag": 0.0},
                ],
                "e_vector": [
                    {"real": e_x, "imag": 0.0},
                    {"real": e_y, "imag": 0.0},
                    {"real": 0.0, "imag": 0.0},
                ],
                "electric_tangential_norm_sq": 1.0,
                "projection_denominator": 2.0,
            }
            for index, (polarization, e_x, e_y) in enumerate(
                (("x", 1.0, 0.0), ("y", 0.0, 1.0))
            )
        ],
    }
    manifest_path = tmp_path / "mode_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True))
    manifest_sha = _manifest_hash(manifest)

    baseline = np.asarray([1.0, 2.0, 0.75 + 1.0j, -0.5j], dtype=np.complex128)
    vectors = {
        "candidate_a6_candidate_h6": baseline.copy(),
        "candidate_a6_native_h6": baseline.copy(),
        "native_a6_candidate_h6": baseline.copy(),
        "native_a6_native_h6": baseline.copy(),
    }
    if perturb_port:
        vectors["native_a6_candidate_h6"][-1] += 1.0e-4
    arrays_path = tmp_path / "first_arnoldi.npz"
    np.savez(arrays_path, **{f"array_{i}": value for i, value in enumerate(vectors.values())})
    pair = {
        name: {"array_key": f"array_{index}", "dtype": str(value.dtype), "shape": list(value.shape)}
        for index, (name, value) in enumerate(vectors.items())
    }
    raw_comparisons = {}
    for name, value in vectors.items():
        raw_relative = float(np.linalg.norm(value - baseline)) / np.linalg.norm(baseline)
        raw_comparisons[name] = {
            "raw_relative_to_combination": raw_relative,
            "raw_limit": 1.0e-10,
            "raw_passed": bool(raw_relative <= 1.0e-10),
        }
    config_path = tmp_path / "resolved.json"
    config_path.write_text(
        json.dumps(
            {
                "derived": {
                    "physical_bounds": {
                        "x_min": 0.0,
                        "x_max": 2.0,
                        "y_min": 0.0,
                        "y_max": 1.0,
                    },
                    "domain_z_min": 0.0,
                    "domain_z_max": 0.0,
                }
            }
        )
    )
    packet = {
        "identity": {
            "source_sha": "e" * 40,
            "ordered_mode_sha256": manifest_sha,
            "expected_space_facts": {"active_rows": 2, "appended_rows": 2},
        },
        "arrays": {
            "path": str(arrays_path),
            "sha256": hashlib.sha256(arrays_path.read_bytes()).hexdigest(),
        },
        "pair": pair,
        "pair_summary": {
            "comparisons_to_candidate_combination": raw_comparisons,
        },
    }
    packet_path = tmp_path / "first_arnoldi.json"
    packet_path.write_text(json.dumps(packet, sort_keys=True))
    return packet_path, manifest_path, config_path, packet, manifest


def test_versioned_offline_checker_reads_saved_vectors_and_manifest(tmp_path):
    packet_path, manifest_path, config_path, _packet, _manifest = (
        _write_saved_checker_case(tmp_path)
    )

    result = check_saved_pair(packet_path, manifest_path, config_path)

    assert result["schema"] == "task40extra.first-arnoldi-hp-gate-check.v1"
    assert result["passed"]
    assert result["raw_euclidean_all_passed"]
    assert result["orthogonality"]["same_order_max_normalized_tangential_overlap"] == 0.0


def test_versioned_offline_checker_rejects_a_physical_port_perturbation(tmp_path):
    packet_path, manifest_path, config_path, _packet, _manifest = (
        _write_saved_checker_case(tmp_path, perturb_port=True)
    )

    result = check_saved_pair(packet_path, manifest_path, config_path)

    assert not result["passed"]
    comparison = result["comparisons"]["native_a6_candidate_h6"]
    assert not comparison["passed"]
    assert not comparison["raw_passed"]
    assert comparison["port_modal_gram_relative"] > result["limit"]


def test_versioned_offline_checker_rejects_wrong_h_and_wrong_mode_order(tmp_path):
    packet_path, manifest_path, config_path, packet, manifest = (
        _write_saved_checker_case(tmp_path)
    )
    manifest["modes"][0]["projection_denominator"] *= 2.0
    manifest_path.write_text(json.dumps(manifest, sort_keys=True))
    packet["identity"]["ordered_mode_sha256"] = _manifest_hash(manifest)
    packet_path.write_text(json.dumps(packet, sort_keys=True))
    with pytest.raises(ValueError, match="H does not match"):
        check_saved_pair(packet_path, manifest_path, config_path)

    packet_path, manifest_path, config_path, packet, manifest = (
        _write_saved_checker_case(tmp_path / "etnorm")
    )
    manifest["modes"][0]["electric_tangential_norm_sq"] *= 2.0
    manifest["modes"][0]["projection_denominator"] *= 2.0
    manifest_path.write_text(json.dumps(manifest, sort_keys=True))
    packet["identity"]["ordered_mode_sha256"] = _manifest_hash(manifest)
    packet_path.write_text(json.dumps(packet, sort_keys=True))
    with pytest.raises(ValueError, match="tangential norm does not match"):
        check_saved_pair(packet_path, manifest_path, config_path)

    packet_path, manifest_path, config_path, packet, manifest = (
        _write_saved_checker_case(tmp_path / "order")
    )
    manifest["modes"].reverse()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True))
    packet["identity"]["ordered_mode_sha256"] = _manifest_hash(manifest)
    packet_path.write_text(json.dumps(packet, sort_keys=True))
    with pytest.raises(ValueError, match="mode order identity mismatch"):
        check_saved_pair(packet_path, manifest_path, config_path)


def test_versioned_offline_checker_rejects_a_wrong_manifest_hash(tmp_path):
    packet_path, manifest_path, config_path, packet, _manifest = (
        _write_saved_checker_case(tmp_path)
    )
    packet["identity"]["ordered_mode_sha256"] = "f" * 64
    packet_path.write_text(json.dumps(packet, sort_keys=True))

    with pytest.raises(ValueError, match="manifest hash mismatch"):
        check_saved_pair(packet_path, manifest_path, config_path)


def test_versioned_offline_checker_rejects_missing_pair_or_raw_fields(tmp_path):
    packet_path, manifest_path, config_path, packet, _manifest = (
        _write_saved_checker_case(tmp_path / "pair")
    )
    packet["pair"].pop("native_a6_native_h6")
    packet_path.write_text(json.dumps(packet, sort_keys=True))
    with pytest.raises(ValueError, match="all four required variants"):
        check_saved_pair(packet_path, manifest_path, config_path)

    packet_path, manifest_path, config_path, packet, _manifest = (
        _write_saved_checker_case(tmp_path / "raw")
    )
    raw_record = packet["pair_summary"]["comparisons_to_candidate_combination"][
        "candidate_a6_native_h6"
    ]
    raw_record.pop("raw_passed")
    raw_record.pop("raw_limit")
    raw_record.pop("raw_relative_to_combination")
    packet_path.write_text(json.dumps(packet, sort_keys=True))
    with pytest.raises(ValueError, match="raw comparison fields are missing"):
        check_saved_pair(packet_path, manifest_path, config_path)
