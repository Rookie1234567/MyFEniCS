from __future__ import annotations

import json
import hashlib

import numpy as np
import pytest

from src.runners import physical_diagnosis_worker
from src.solvers.task40_v20_local_components import (
    _array_sha256,
    _save_component_packet,
    _validate_reused_local_prefix,
    verify_v20_saved_c00_packet,
)


def _sample_arrays():
    return {
        "matrix": np.arange(12, dtype=np.complex128).reshape(3, 4) * (1 + 2j),
        "rhs": np.asarray([2 + 3j, 5 - 7j], dtype=np.complex128),
    }


def test_v20_component_packet_round_trips_business_names_to_npz_keys(tmp_path):
    arrays = _sample_arrays()

    receipt = _save_component_packet(
        tmp_path,
        "roundtrip",
        {"purpose": "real save_packet readback fixture"},
        arrays,
    )

    record = json.loads((tmp_path / "roundtrip.json").read_text(encoding="utf-8"))
    descriptors = record["raw_arrays"]
    assert set(descriptors) == set(arrays)
    assert {item["array_key"] for item in descriptors.values()} == {
        "array_0",
        "array_1",
    }
    assert set(receipt["arrays"]) == set(arrays)
    assert receipt["write_and_readback_hash_passed"] is True
    with np.load(tmp_path / "roundtrip.npz", allow_pickle=False) as archive:
        assert set(archive.files) == {item["array_key"] for item in descriptors.values()}
        for name, expected in arrays.items():
            descriptor = descriptors[name]
            actual = archive[descriptor["array_key"]]
            assert actual.shape == expected.shape
            assert actual.dtype == expected.dtype
            assert _array_sha256(actual) == _array_sha256(expected)
            assert receipt["arrays"][name]["sha256"] == _array_sha256(expected)


@pytest.mark.parametrize("corruption", ["omitted", "duplicate"])
def test_v20_component_packet_rejects_incomplete_or_reused_array_keys(
    tmp_path, monkeypatch, corruption
):
    save_packet = physical_diagnosis_worker.save_packet

    def save_then_corrupt(directory, name, facts):
        save_packet(directory, name, facts)
        path = directory / f"{name}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        if corruption == "omitted":
            record["raw_arrays"].pop("rhs")
        else:
            record["raw_arrays"]["rhs"]["array_key"] = record["raw_arrays"]["matrix"][
                "array_key"
            ]
        path.write_text(json.dumps(record), encoding="utf-8")

    monkeypatch.setattr(physical_diagnosis_worker, "save_packet", save_then_corrupt)
    with pytest.raises(RuntimeError, match="inventory|repeated"):
        _save_component_packet(
            tmp_path,
            "corrupt",
            {},
            _sample_arrays(),
        )


def test_v20_saved_c00_reuse_replays_matrix_schur_and_full_recovery_equations(tmp_path):
    Vii = np.diag(np.asarray([2.0, 3.0], dtype=np.complex128))
    Vit = np.asarray([[1.0], [2.0]], dtype=np.complex128)
    Vti = np.asarray([[1.0, 2.0]], dtype=np.complex128)
    Vtt = np.asarray([[8.0]], dtype=np.complex128)
    xi = np.asarray([0.5, -0.25], dtype=np.complex128)
    xt = np.asarray([2.0], dtype=np.complex128)
    solved = np.linalg.solve(Vii, Vit)
    solved_xt = np.linalg.solve(Vii, Vit @ xt)
    full_rhs = Vii @ xi + Vit @ xt
    reduced_rhs = full_rhs - Vit @ xt
    arrays = {
        "Vii": Vii,
        "Vit": Vit,
        "Vti": Vti,
        "Vtt": Vtt,
        "Schur": Vtt - Vti @ solved,
        "known_xi": xi,
        "known_xt": xt,
        "interior_rhs": reduced_rhs,
        "recovered_xi": xi,
        "solved_Vit": solved,
        "solved_Vit_xt": solved_xt,
    }
    inventory = {
        "named_array_payload_bytes_with_aliases": 4096,
        "unique_backing_bytes": 3072,
    }
    facts = {
        "class_id": "c00",
        "status": "PASS",
        "passed": True,
        "gates": {"local_equation": True, "forward": True},
        "metric_identity": {"cell_permutation": 0},
        "material_tag": 1,
        "target_cell_count": 1,
        "filled_reference_cell_count": 1,
        "array_inventory": inventory,
    }
    packet = _save_component_packet(tmp_path, "v20_local_c00", facts, arrays)
    packet_json = tmp_path / "v20_local_c00.json"
    packet_npz = tmp_path / "v20_local_c00.npz"
    json_sha = hashlib.sha256(packet_json.read_bytes()).hexdigest()
    npz_sha = hashlib.sha256(packet_npz.read_bytes()).hexdigest()
    receipt = {
        "classification": "SUPPLEMENTAL_ARTIFACT_READBACK_ONLY",
        "json_sha256": json_sha,
        "archive_sha256": npz_sha,
        "current_source_head": "a" * 40,
        "run_directory": str(tmp_path.resolve()),
        "per_array_expected_hash_basis": (
            "loaded from preserved NPZ for key-mapping integrity replay; not an independent pre-save hash"
        ),
        "readback": packet,
    }
    receipt_path = tmp_path / "readback_receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()

    reused, validation = verify_v20_saved_c00_packet(
        tmp_path,
        receipt_path,
        expected_json_sha256=json_sha,
        expected_npz_sha256=npz_sha,
        expected_readback_receipt_sha256=receipt_sha,
    )

    assert reused["class_id"] == "c00"
    assert reused["raw_packet"]["write_and_readback_hash_passed"] is True
    assert validation["passed"] is True
    assert validation["independent_matrix_and_recovery_replay"][
        "recovery_full_original_equation_relative"
    ] < 1.0e-14
    assert validation["independent_matrix_and_recovery_replay"][
        "recovery_reduced_original_equation_relative"
    ] < 1.0e-14


def test_v20_reused_local_prefix_rejects_a_wrong_class_identity():
    classes = [
        {
            "class_id": "c00",
            "metric_identity": {"cell_permutation": 0},
            "material_tag": 1,
            "target_cell_count": 1,
            "filled_reference_cell_count": 1,
        }
    ]
    reused = {
        "class_id": "c01",
        "metric_identity": {"cell_permutation": 0},
        "material_tag": 1,
        "target_cell_count": 1,
        "filled_reference_cell_count": 1,
        "passed": True,
    }
    with pytest.raises(ValueError, match="geometry inventory"):
        _validate_reused_local_prefix(classes, [reused])
