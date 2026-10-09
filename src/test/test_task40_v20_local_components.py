from __future__ import annotations

import json

import numpy as np
import pytest

from src.runners import physical_diagnosis_worker
from src.solvers.task40_v20_local_components import _array_sha256, _save_component_packet


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
