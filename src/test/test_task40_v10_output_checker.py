import json
import numpy as np
import pytest
from types import SimpleNamespace

from src.runners.physical_diagnosis_worker import save_packet
from src.runners.task40_v10_worker import _save_packet
from src.runners.task40_v10_output_checker import (
    verify_v10_output_bundle,
    verify_v10_regular_internal_witness,
)


def test_v10_output_checker_reopens_field_identity_and_recomputes_residual(tmp_path):
    field_path = tmp_path / "field.vtu"
    field_path.write_bytes(b"tiny field fixture")
    import hashlib

    file_digest = hashlib.sha256(field_path.read_bytes()).hexdigest()
    rhs = np.array([3 + 0j, 4 + 0j], dtype=np.complex128)
    applied = np.array([1 + 0j, 0 + 0j], dtype=np.complex128)
    residual = rhs - applied
    relative = float(np.linalg.norm(residual) / np.linalg.norm(rhs))
    save_packet(
        tmp_path,
        "residual",
        {
            "relative_residual": relative,
            "native_witness_relative_residual": relative,
            "limit": 1.0,
            "full_physical_rhs_storage": rhs,
            "full_solution_storage": np.array([0.5 + 0j, 0.25 + 0j]),
            "target_backend_applied_storage": applied,
            "target_backend_residual_storage": residual,
            "native_witness_applied_storage": applied,
            "native_witness_residual_storage": residual,
        },
    )
    save_packet(
        tmp_path,
        "output",
        {
            "scientific_identity": {
                "full_solution_packet_json": str(tmp_path / "residual.json"),
                "full_solution_storage_sha256": "a" * 64,
                "ordered_physical_mode_sha256": "b" * 64,
                "field_mode_and_diffraction_files": [
                    {
                        "path": str(field_path),
                        "size_bytes": field_path.stat().st_size,
                        "sha256": file_digest,
                    }
                ],
            }
        },
    )
    result = verify_v10_output_bundle(tmp_path / "output.json")
    residual_record = json.loads((tmp_path / "residual.json").read_text())
    output_record = json.loads((tmp_path / "output.json").read_text())
    assert result["status"] == "PASS"
    assert all(row["passed"] for row in result["residual_checks"])
    assert result["field_mode_and_diffraction_file_checks"][0]["passed"]
    assert residual_record["arrays"]["sha256"]
    assert output_record["scientific_identity"]["full_solution_storage_sha256"] == "a" * 64


def test_nested_checkpoint_packet_creates_parent_and_roundtrips(tmp_path):
    runtime = SimpleNamespace(directory=tmp_path, markers=[])
    runtime.marker = lambda name, facts: runtime.markers.append((name, facts))
    runtime.reserve_workspace = lambda *_args: None
    runtime.release_workspace = lambda *_args: None
    vector = np.array([1 + 0j, 2 + 3j], dtype=np.complex128)
    packet = _save_packet(
        runtime,
        "checkpoints/v10_candidate_p6_x_0000_0001",
        {"solution_storage": vector},
    )
    assert (tmp_path / "checkpoints/v10_candidate_p6_x_0000_0001.json").is_file()
    with np.load(packet["arrays"]["path"], allow_pickle=False) as arrays:
        np.testing.assert_array_equal(arrays["array_0"], vector)
    assert any(name == "v10_raw_disk_admission" for name, _facts in runtime.markers)


def _regular_internal_payload(
    *,
    limit=1.0e-11,
    action_offset=1.0e-12 + 1.0e-12j,
    residual_override=None,
    operation_scale=None,
    stored_relative=None,
):
    count = 36_000
    effective_rhs = np.ones(count, dtype=np.complex128)
    saved_action = effective_rhs - action_offset
    residual = effective_rhs - saved_action
    if operation_scale is None:
        operation_scale = 2.0 * float(np.linalg.norm(effective_rhs))
    if stored_relative is None:
        stored_relative = float(np.linalg.norm(residual) / operation_scale)
    return {
        "full_internal_effective_rhs": effective_rhs,
        "full_internal_saved_field_action": saved_action,
        "full_internal_recovery_residuals": (
            residual if residual_override is None else residual_override
        ),
        "full_internal_original_rows": np.tile(np.arange(count // 2, dtype=np.int64), 2),
        "full_internal_twist_indices": np.repeat(np.array([0, 1], dtype=np.int8), count // 2),
        "full_internal_recovery_rows": count,
        "full_internal_recovery_operation_scale": operation_scale,
        "full_internal_recovery_limit": limit,
        "full_internal_recovery_relative": stored_relative,
    }


def test_regular_internal_checker_recomputes_residual_from_raw_arrays(tmp_path):
    payload = _regular_internal_payload()
    save_packet(tmp_path, "regular_internal", payload)
    packet = json.loads((tmp_path / "regular_internal.json").read_text())

    result = verify_v10_regular_internal_witness(tmp_path / "regular_internal.json")

    assert result["passed"]
    assert result["internal_row_count"] == 36_000
    assert result["residual_algebra_defect_relative"] == 0.0
    assert result["packet_npz_sha256"] == packet["arrays"]["sha256"]


def test_regular_internal_checker_rejects_forged_saved_residual(tmp_path):
    count = 36_000
    payload = _regular_internal_payload(
        action_offset=1.0e-4,
        residual_override=np.zeros(count, dtype=np.complex128),
        operation_scale=1.0e16,
        stored_relative=0.0,
    )
    save_packet(tmp_path, "forged_regular_internal", payload)

    with pytest.raises(ValueError, match="failed raw-array recomputation"):
        verify_v10_regular_internal_witness(tmp_path / "forged_regular_internal.json")


def test_regular_internal_checker_rejects_relaxed_limit(tmp_path):
    save_packet(
        tmp_path,
        "relaxed_regular_internal",
        _regular_internal_payload(limit=1.0e-6),
    )

    with pytest.raises(ValueError, match="fixed 1e-11 contract"):
        verify_v10_regular_internal_witness(tmp_path / "relaxed_regular_internal.json")
