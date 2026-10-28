"""Targeted, non-PDE tests for the frozen V19 saved-field diagnostic."""
from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from benchmarks.task43_hp_adaptivity import analyze_saved_hp_response as checker


@pytest.fixture(scope="session", autouse=True)
def _qualified_worker_identity():
    stage = os.environ.get("TASK43_V19_STAGE", "")
    if stage not in ("T1", "T2"):
        pytest.skip("V19 test nodes run only inside the checked T worker")
    checker.write_runtime_identity(stage, "start")
    try:
        yield
    finally:
        checker.write_runtime_identity(stage, "end")


def _array_digest(array: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(contiguous.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(contiguous.shape)).encode("ascii"))
    digest.update(contiguous.tobytes(order="C"))
    return digest.hexdigest()


def _npy_bytes(array: np.ndarray) -> bytes:
    stream = io.BytesIO()
    np.save(stream, np.asarray(array), allow_pickle=False)
    return stream.getvalue()


def _archive(
    path: Path, schema: str, identity: dict[str, Any], arrays: dict[str, np.ndarray]
) -> tuple[str, str, dict[str, dict[str, Any]]]:
    array_records = {}
    payloads = {}
    for name, value in arrays.items():
        array = np.ascontiguousarray(value)
        array_records[name] = {
            "dtype": array.dtype.str,
            "shape": list(array.shape),
            "sha256": _array_digest(array),
        }
        payloads[f"{name}.npy"] = _npy_bytes(array)
    record_payload = json.dumps(
        {"schema": schema, "identity": identity, "arrays": array_records},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    payloads[f"{checker.NPY_RECORD_KEY}.npy"] = _npy_bytes(
        np.frombuffer(record_payload, dtype=np.uint8)
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in payloads.items():
            archive.writestr(name, value)
    return (
        checker.sha256_file(path), hashlib.sha256(record_payload).hexdigest(), array_records
    )


def _modal_rows() -> list[dict[str, Any]]:
    rows = []
    for side, m, n, pol in checker.CHANNEL_KEYS:
        rows.append({
            "side": side,
            "order_m": m,
            "order_n": n,
            "polarization": pol,
            "outgoing_amplitude_at_boundary": [0.25, -0.125],
            "outgoing_amplitude": [0.25, -0.125],
            "power_ratio": 1.0e-4,
            "modal_power_code_units": 1.0,
            "R": 1.0e-4 if side == "top" else 0.0,
            "T": 1.0e-4 if side == "bottom" else 0.0,
            "propagating": True,
        })
    return rows


def _modal_cases() -> dict[str, dict[tuple[str, int, int, str], dict[str, Any]]]:
    baseline = checker.modal_inventory(_modal_rows())
    cases = {name: {key: dict(row) for key, row in baseline.items()}
             for name in ("R9", "H8", "P8", "Y6_1")}
    special = ("top", 0, 0, "s")
    cases["Y6_1"][special]["power_ratio"] = 0.001
    cases["R9"][special]["power_ratio"] = 0.0009
    cases["H8"][special]["power_ratio"] = 0.001002
    cases["P8"][special]["power_ratio"] = 0.001003
    cases["H8"][special]["outgoing_amplitude_at_boundary"] = [0.25, -0.124]
    cases["P8"][special]["outgoing_amplitude_at_boundary"] = [0.251, -0.125]
    return cases


def test_weighted_multicell_terms_close_after_reordering():
    e = np.array([[1.0 + 2.0j, -0.5j], [0.5 - 0.25j, 1.0],
                  [2.0j, 0.75 + 0.5j], [1.25, -1.5j]])
    delta = np.array([[0.25j, 0.5], [-0.25, 0.125j],
                      [0.5 - 0.25j, -0.75], [0.25j, 0.5]])
    weights = np.array([0.25, 0.75, 1.5, 2.0])
    owners = np.array([0, 1, 0, 1])
    order = np.array([2, 0, 3, 1])
    original = checker._accumulate_component(e, delta, weights, owners, 2, 1.7)
    reordered = checker._accumulate_component(
        e[order], delta[order], weights[order], owners[order], 2, 1.7
    )
    for key in original:
        np.testing.assert_allclose(original[key], reordered[key], rtol=2e-14, atol=2e-14)
    scale = np.maximum.reduce([
        original["B"], original["after_error_squared"], np.abs(original["X"]),
        original["D"], np.full(2, 1e-30),
    ])
    assert np.all(np.abs(original["identity_error"]) <= 1e-12 * scale)
    boxes = [
        {"lower": [0.0, 0.0, 0.0], "upper": [1.0, 1.0, 1.0]},
        {"lower": [1.0, 0.0, 0.0], "upper": [2.0, 1.0, 1.0]},
    ]
    groups = {0: "requested_root4_global8", 1: "rest_of_domain"}
    rows = checker._cell_csv_rows(8, boxes, [0, 1], groups, {"P8": {"E": original}}, 2.0, 3.0)
    assert len(rows) == 2
    assert len(rows[0]) == 27
    assert rows[0]["P8.E.I"] == pytest.approx(original["I"][0])
    assert rows[0]["P8.E.direction_correlation"] == pytest.approx(
        original["X"][0] / (2.0 * np.sqrt(original["B"][0] * original["D"][0]))
    )


@pytest.mark.parametrize(
    ("delta", "expected_cross", "expected_i"),
    [(1.0 + 0.0j, 2.0, 1.0), (-1.0 + 0.0j, -2.0, -3.0),
     (0.0 + 1.0j, 0.0, -1.0)],
    ids=("aligned", "opposite", "orthogonal"),
)
def test_response_direction_cases(delta, expected_cross, expected_i):
    result = checker._accumulate_component(
        np.array([1.0 + 0.0j]), np.array([delta]),
        np.array([1.0]), np.array([0]), 1, 1.0,
    )
    assert result["X"][0] == pytest.approx(expected_cross)
    assert result["I"][0] == pytest.approx(expected_i)
    assert result["I_independent"][0] == pytest.approx(expected_i)


def test_domain_cancellation_and_zero_increment():
    weights = np.array([1.0, 1.0])
    owners = np.array([0, 1])
    deltas = np.array([1.0 + 0.0j, 1.0 - np.sqrt(2.0) + 0.0j])
    cancellation = checker._accumulate_component(
        np.ones(2, dtype=np.complex128), deltas, weights, owners, 2, 1.0,
    )
    np.testing.assert_allclose(cancellation["I"], [1.0, -1.0], atol=2e-15)
    np.testing.assert_allclose(cancellation["I_independent"], [1.0, -1.0], atol=2e-15)
    summary = checker._block_summaries(
        [0, 1], {0: "requested_root4_global8", 1: "rest_of_domain"},
        {"P8": {"E": cancellation}},
    )
    requested = summary["requested_root4_global8"]["P8"]["E"]
    rest = summary["rest_of_domain"]["P8"]["E"]
    assert requested["I"] == pytest.approx(1.0)
    assert rest["I"] == pytest.approx(-1.0)
    assert requested["positive_I_sum"] == pytest.approx(1.0)
    assert rest["negative_I_sum"] == pytest.approx(-1.0)
    assert summary["rest_of_domain"]["P8"]["E"]["cancellation_fraction"] == pytest.approx(0.0)
    unchanged = checker._accumulate_component(
        np.ones(2, dtype=np.complex128), np.zeros(2, dtype=np.complex128),
        weights, owners, 2, 1.0,
    )
    np.testing.assert_allclose(unchanged["D"], [0.0, 0.0])
    np.testing.assert_allclose(unchanged["I"], [0.0, 0.0])
    np.testing.assert_allclose(unchanged["after_error_squared"], unchanged["B"])


def test_channel_reference_inventory_is_exact():
    contract_path = checker.REPO_ROOT / checker.CONTRACT_RELATIVE_PATH
    contract, _ = checker._load_manifest(contract_path)
    saved_bundle = checker._load_source_bundle(contract)
    assert set(saved_bundle["modal"]) == {"R9", "H8", "P8", "Y6_1"}
    assert all(len(rows) == 612 for rows in saved_bundle["modal"].values())
    assert set(saved_bundle["absorption"]) == {"R9", "H8", "P8", "Y6_1"}
    assert set(saved_bundle["comparison"]["results"]) == {"q8", "q10"}
    cases = _modal_cases()
    for rows in cases.values():
        assert set(rows) == set(checker.CHANNEL_KEYS)
        assert len(rows) == 612
    mode_rows, exceed = checker._mode_rows(cases, 1.0e-6)
    assert len(mode_rows) == 612
    assert len(exceed) == 3
    key = next(row for row in mode_rows if (row["side"], row["m"], row["n"], row["polarization"]) == ("top", 0, 0, "s"))
    for action in ("H8", "P8"):
        assert f"{action}_minus_R9_power_ratio_signed" in key
        assert f"{action}_minus_Y6_1_power_ratio_signed" in key
        assert f"{action}_minus_R9_power_ratio_absolute" in key
        assert f"{action}_minus_Y6_1_power_ratio_absolute" in key
        assert f"{action}_minus_Y6_1_amplitude_real" in key
        assert f"{action}_minus_Y6_1_power_exceeds_threshold" in key
    evanescent = ("bottom", 4, 8, "p")
    for case in cases.values():
        case[evanescent]["outgoing_amplitude_at_boundary"] = [0.0, 0.0]
        case[evanescent]["power_ratio"] = 0.0
        case[evanescent]["propagating"] = False
    zero_modes, _ = checker._mode_rows(cases, 1.0e-6)
    zero_row = next(row for row in zero_modes if (row["side"], row["m"], row["n"], row["polarization"]) == evanescent)
    assert zero_row["R9_amplitude_real"] == 0.0
    assert zero_row["R9_saved_power_ratio"] == 0.0
    assert zero_row["H8_propagating"] is False


def test_wrong_owner_map_is_rejected():
    checker.validate_owner_map(np.array([4, 9]), np.array([0, 1, 0]), np.array([4, 9, 4]))
    with pytest.raises(checker.EvidenceError, match="owner global ids"):
        checker.validate_owner_map(
            np.array([4, 9]), np.array([0, 1, 0]), np.array([4, 9, 9])
        )


def test_modal_missing_key_is_rejected():
    rows = _modal_rows()
    with pytest.raises(checker.EvidenceError, match="exact 612-channel set"):
        checker.modal_inventory(rows[:-1])


def test_modal_duplicate_key_is_rejected():
    rows = _modal_rows()
    rows.append(dict(rows[0]))
    with pytest.raises(checker.EvidenceError, match="duplicate modal key"):
        checker.modal_inventory(rows)


def test_mixed_sample_package_rebound_hash_is_rejected(tmp_path: Path):
    points = np.array([[1.0, 2.0, 3.0], [2.0, 3.0, 4.0]], dtype=np.float64)
    weights = np.array([0.5, 0.5], dtype=np.float64)
    p5_path = tmp_path / "p5.npz"
    p5_sha, p5_record_sha, p5_arrays = _archive(
        p5_path, "task43.fixture.p5.v1",
        {"quadrature_order": 8, "reference_label": "Y6_1", "sample_count": 2},
        {"points_nm": points, "weights_nm3": weights},
    )
    p5_identity = {"quadrature_order": 8, "reference_label": "Y6_1", "sample_count": 2}
    p5_record = checker.inspect_npz(
        p5_path, outer_sha256=p5_sha, expected_members={"points_nm", "weights_nm3"},
        expected_count=2, expected_schema="task43.fixture.p5.v1",
        expected_identity=p5_identity, expected_nested_identity={},
        expected_record_sha256=p5_record_sha,
    )
    checker.verify_pair_identity(p5_record, {
        "identity": {
            "quadrature_order": 8, "sample_count": 2,
            "P5_sample_sha256": p5_sha, "P8_sampled_once": True,
            "candidate_identity": {"candidate_id": "v16_r9_p8"},
            "point_identity": {"sha256": p5_arrays["points_nm"]["sha256"]},
            "weight_identity": {"sha256": p5_arrays["weights_nm3"]["sha256"]},
        },
    }, p5_sha, "v16_r9_p8", 8)
    p8_arrays = {"P8_E": np.array([[0.1 + 0.2j], [0.3 + 0.4j]], dtype=np.complex128)}
    p8_path = tmp_path / "p8_mixed.npz"
    p8_identity = {
        "quadrature_order": 8, "sample_count": 2,
        "P5_sample_sha256": "0" * 64, "P8_sampled_once": True,
        "candidate_identity": {"candidate_id": "v16_r9_p8"},
        "point_identity": {"sha256": p5_arrays["points_nm"]["sha256"]},
        "weight_identity": {"sha256": p5_arrays["weights_nm3"]["sha256"]},
    }
    p8_sha, p8_record_sha, _ = _archive(
        p8_path, "task43.fixture.p8.v1", p8_identity, p8_arrays
    )
    p8_record = checker.inspect_npz(
        p8_path, outer_sha256=p8_sha, expected_members={"P8_E"},
        expected_count=2, expected_schema="task43.fixture.p8.v1",
        expected_identity={
            "quadrature_order": 8, "sample_count": 2,
            "P5_sample_sha256": "0" * 64, "P8_sampled_once": True,
        },
        expected_nested_identity={
            "candidate_identity.candidate_id": "v16_r9_p8",
            "point_identity.sha256": p5_arrays["points_nm"]["sha256"],
            "weight_identity.sha256": p5_arrays["weights_nm3"]["sha256"],
        },
        expected_record_sha256=p8_record_sha,
    )
    with pytest.raises(checker.EvidenceError, match="mixed with a different P5"):
        checker.verify_pair_identity(p5_record, p8_record, p5_sha, "v16_r9_p8", 8)
    p5_wrong_reference_path = tmp_path / "p5_wrong_reference.npz"
    wrong_ref_sha, wrong_ref_record_sha, _ = _archive(
        p5_wrong_reference_path, "task43.fixture.p5.v1",
        {"quadrature_order": 8, "reference_label": "R9", "sample_count": 2},
        {"points_nm": points, "weights_nm3": weights},
    )
    wrong_ref = checker.inspect_npz(
        p5_wrong_reference_path, outer_sha256=wrong_ref_sha,
        expected_members={"points_nm", "weights_nm3"}, expected_count=2,
        expected_schema="task43.fixture.p5.v1",
        expected_identity={"quadrature_order": 8, "reference_label": "R9", "sample_count": 2},
        expected_nested_identity={}, expected_record_sha256=wrong_ref_record_sha,
    )
    with pytest.raises(checker.EvidenceError, match="reference must remain Y6_1"):
        checker.verify_pair_identity(wrong_ref, p8_record, p5_sha, "v16_r9_p8", 8)


def test_amplitude_square_identity_is_not_physical_power():
    reference = 3.0 + 4.0j
    delta = -2.0 + 0.5j
    result = checker.amplitude_square_delta(reference, delta)
    assert result["amplitude_squared_change"] == pytest.approx(
        abs(reference + delta) ** 2 - abs(reference) ** 2
    )
    assert "power" not in result


def test_archive_readonly_and_q8_survives_q10_write_failure(tmp_path: Path):
    input_path = tmp_path / "saved_input.npz"
    source_record = np.frombuffer(b"fixture-only record", dtype=np.uint8)
    np.savez(
        input_path,
        field=np.array([[1.0 + 0.0j]], dtype=np.complex128),
        **{checker.NPY_RECORD_KEY: source_record},
    )
    before_input = checker.sha256_file(input_path)
    arrays = checker._load_npz_arrays(input_path, {"field"})
    assert arrays["field"].flags.writeable is False
    assert checker.sha256_file(input_path) == before_input

    output_root = tmp_path / "source_run"
    output_root.mkdir()
    cell_rows = [{"global_cell_id": 8, "response": 1.25}]
    mode_rows = [{"side": "top", "m": 0, "n": 0, "polarization": "s"}]
    q8_record = checker._persist_order_outputs(
        output_root, "q8", {"quadrature": {"order": 8}, "status": "COMPLETE"},
        cell_rows, mode_rows,
    )
    contract = {"sources": {}, "quadrature_archives": {}}
    (output_root / "run_manifest.json").write_text(json.dumps({
        "schema": "task43.v19.saved_hp_response_run.v1",
        "checker_sha256": checker.sha256_file(Path(checker.__file__)),
        "source_sha256_start": {}, "source_sha256_end": {},
        "orders": {"q8": q8_record},
    }), encoding="utf-8")
    q8_paths = [Path(q8_record[key]["path"]) for key in ("diagnostic", "cells_csv", "modes_612_csv")]
    q8_before = {str(path): checker.sha256_file(path) for path in q8_paths}
    (output_root / "q10").mkdir()
    with pytest.raises(FileExistsError):
        checker._persist_order_outputs(
            output_root, "q10", {"quadrature": {"order": 10}}, cell_rows, mode_rows
        )
    assert {str(path): checker.sha256_file(path) for path in q8_paths} == q8_before
    resumed = checker.resume_completed_order(output_root, contract, order="q8")
    assert resumed["status"] == "COMPLETE"
    assert resumed["reused_from"]["order"] == "q8"
