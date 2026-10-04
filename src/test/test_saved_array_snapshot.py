from benchmarks.check_saved_array_snapshot import verify_saved_snapshot

import copy
import hashlib

import numpy as np
import pytest


def saved_fixture(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    members = []
    for name, value in [("C", np.arange(15, dtype=np.float64).reshape(3, 5)),
                        ("F", np.asfortranarray(np.arange(12).reshape(3, 4) * (1 + 2j)))]:
        path = raw / (hashlib.sha256(name.encode()).hexdigest() + ".npy")
        np.save(path, value, allow_pickle=False)
        digest = hashlib.sha256(repr((value.shape, str(value.dtype))).encode() + value.tobytes(order="C"))
        members.append({"name": name, "shape": list(value.shape), "dtype": str(value.dtype),
                        "numeric_bytes": value.nbytes, "sha256": digest.hexdigest(),
                        "callback_reference": str(path)})
    numeric = sum(m["numeric_bytes"] for m in members)
    roles = {m["name"]: m for m in members}
    roles["alias"] = members[0]
    return raw, {"snapshot": {"members": members, "roles": roles,
                             "unique_member_count": len(members), "numeric_bytes": numeric,
                             "archive_members_bytes_upper": numeric + 4096 * len(members),
                             "archive_payload_limit_bytes": 2**20}}


def test_c_and_fortran_readback_with_aliases(tmp_path):
    raw, report = saved_fixture(tmp_path)
    result = verify_saved_snapshot(report, raw)
    assert result["verified"] and result["unique_member_count"] == 2
    assert result["logical_role_count"] == 3
    assert result["new_FE_actions"] == result["new_solves"] == result["new_factors"] == 0
    assert not result["power_failure_tested"] and not result["cross_machine_storage_qualified"]


def test_changed_payload_and_trailing_data_rejected(tmp_path):
    raw, report = saved_fixture(tmp_path)
    path = next(raw.iterdir())
    value = np.load(path, mmap_mode="r+")
    value[0, 0] += 1
    value.flush()
    value._mmap.close()
    with pytest.raises(ValueError, match="digest"):
        verify_saved_snapshot(report, raw)
    with path.open("ab") as stream:
        stream.write(b"extra")
    with pytest.raises(ValueError, match="extent"):
        verify_saved_snapshot(report, raw)


def test_partial_role_inventory_and_false_budget_rejected(tmp_path):
    raw, report = saved_fixture(tmp_path)
    missing = copy.deepcopy(report)
    del missing["snapshot"]["roles"]["F"]
    with pytest.raises(ValueError, match="orphan"):
        verify_saved_snapshot(missing, raw)
    false = copy.deepcopy(report)
    false["snapshot"]["numeric_bytes"] += 1
    with pytest.raises(ValueError, match="budget"):
        verify_saved_snapshot(false, raw)


def test_extra_file_and_escaped_binding_rejected(tmp_path):
    raw, report = saved_fixture(tmp_path)
    (raw / "unexpected").write_bytes(b"unbound")
    with pytest.raises(ValueError, match="extra"):
        verify_saved_snapshot(report, raw)
    (raw / "unexpected").unlink()
    report["snapshot"]["members"][0]["callback_reference"] = str(tmp_path / "outside.npy")
    with pytest.raises(ValueError, match="canonical raw"):
        verify_saved_snapshot(report, raw)
