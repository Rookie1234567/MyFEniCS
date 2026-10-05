import json
import numpy as np
from types import SimpleNamespace

from src.runners.physical_diagnosis_worker import save_packet
from src.runners.task40_v10_worker import _save_packet
from src.runners.task40_v10_output_checker import verify_v10_output_bundle


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
