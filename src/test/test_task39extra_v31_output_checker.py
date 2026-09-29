"""Raw-output fixtures for the V31 authority-limited result checker."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from benchmarks.task39extra_v31_output_checker import EXPECTED_RUN_ID, check_run


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _residual_packet(root: Path, directory: str) -> dict:
    packet_dir = root / directory
    packet_dir.mkdir(parents=True)
    archive = packet_dir / "q4.npz"
    rhs = np.array([1.0 + 0.0j], dtype=np.complex128)
    applied = np.array([1.0 - 1.0e-8 + 0.0j], dtype=np.complex128)
    residual = rhs - applied
    solution = np.array([1.0 + 0.0j], dtype=np.complex128)
    np.savez_compressed(archive, array_0=rhs, array_1=solution, array_2=applied, array_3=residual)
    return {
        "arrays": {"path": str(archive), "sha256": _sha(archive)},
        "rhs": {"array_key": "array_0"},
        "solution": {"array_key": "array_1"},
        "applied": {"array_key": "array_2"},
        "residual": {"array_key": "array_3"},
        "rhs_norm": 1.0,
        "explicit_relative_residual": float(np.linalg.norm(residual)),
        "independent_action_count": 1,
    }


def _fixture(root: Path) -> Path:
    root.mkdir()
    (root / "input_original.dat").write_text("fixture input\n", encoding="utf-8")
    source_sha = "fixture-source"
    (root / "source_sha.txt").write_text(source_sha + "\n", encoding="utf-8")
    input_sha = _sha(root / "input_original.dat")
    _write_json(root / "run_manifest.json", {
        "status": "finished", "exit_status": 0, "run_id": EXPECTED_RUN_ID,
        "source_sha": source_sha, "input_sha256": input_sha,
    })
    _write_json(root / "run_summary.json", {
        "status": "finished", "exit_status": 0, "run_id": EXPECTED_RUN_ID,
    })
    _write_json(root / "resolved_config.json", {"run_id": EXPECTED_RUN_ID})

    final = _residual_packet(root, "final_residual")
    released = _residual_packet(root, "post_release_final_residual")
    _write_json(root / "final_residual/q4_final.json", final)
    _write_json(root / "post_release_final_residual/q4_post_release_final.json", released)
    ratio = final["explicit_relative_residual"]
    _write_json(root / "physical_dual_condensed_projection_layout_v31_summary.json", {
        "source_sha": source_sha,
        "result_classification": "DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED",
        "official_result": True,
        "release_after_final_residual": True,
        "final_explicit_relative_residual": ratio,
        "post_release_explicit_relative_residual": ratio,
        "reference_authority": "MATCHED_REFERENCE_NOT_AVAILABLE",
        "reference_evaluation": {"attempted": False},
    })

    official_dir = root / "official_output"
    official_dir.mkdir()
    official_archive = official_dir / "q4_output.npz"
    np.savez_compressed(official_archive, array_0=np.zeros(80, dtype=np.complex128))
    _write_json(official_dir / "q4_output.json", {
        "arrays": {"sha256": _sha(official_archive)},
        "output": {"auxiliary": {"array_key": "array_0"}},
    })

    modes = []
    orders = []
    for index in range(80):
        modes.append({
            "side": "top" if index < 40 else "bottom",
            "m": index // 2,
            "n": 0,
            "polarization": "s" if index % 2 == 0 else "p",
        })
        orders.append({**modes[-1], "R": 0.0, "T": 0.0, "power_ratio": 0.0})
    _write_json(root / "v31q4_ordered_mode_manifest.json", {"modes": modes, "mode_count": 80})
    _write_json(root / "numerical_output/dtn_port_diffraction_orders_3d.json", {"orders": orders})
    _write_json(root / "numerical_output/dtn_auxiliary_amplitudes_3d.json", [0.0] * 80)
    power = {
        "R_total": 0.0, "T_total": 0.0, "R_plus_T": 0.0, "A_balance": 1.0,
        "R00_s": 0.0, "R00_p": 0.0, "R00_total": 0.0,
    }
    _write_json(root / "numerical_output/dtn_port_power_metrics_3d.json", power)
    _write_json(root / "numerical_output/port_power.json", power)
    _write_json(root / "numerical_output/volume_absorption.json", {
        "A_volume_total": 1.0,
        "A_volume_grating": 0.5,
        "A_volume_substrate": 0.5,
    })
    return root


def test_v31_raw_output_checker_recomputes_residual_modes_and_energy(tmp_path: Path):
    result = check_run(_fixture(tmp_path / "run"))

    assert result["status"] == "PASS_WITH_AUTHORITY_LIMITATION"
    assert result["failures"] == []
    assert result["checks"]["final_explicit_residual"] is True
    assert result["checks"]["ordered_modal_identity"] is True
    assert result["checks"]["energy_and_absorption_closure"] is True
    assert (
        result["qualification"]["field_error_l2_and_curl"]
        == "NOT_ATTEMPTED_NO_MATCHED_REFERENCE"
    )


def test_v31_raw_output_checker_rejects_modal_order_or_power_drift(tmp_path: Path):
    root = _fixture(tmp_path / "run")
    path = root / "numerical_output/dtn_port_diffraction_orders_3d.json"
    modal = json.loads(path.read_text(encoding="utf-8"))
    modal["orders"][1]["m"] = 999
    _write_json(path, modal)

    result = check_run(root)

    assert result["status"] == "RAW_OUTPUT_CHECK_FAIL"
    assert "ordered_modal_identity" in result["failures"]
