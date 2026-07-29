from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks.check_case112_task002 import build_scaffold_record
from benchmarks.run_task032_phase6_augmented import _parse_args
from src.forward_data.orders import FIXED_M_ORDERS
from src.forward_data.task002_campaign import (
    _parser, load_manifest, sample_key, task002_hybrid_command, update_manifest,
)
from src.forward_data.task002_dataset import verify_compact_dataset, write_compact_dataset
from src.forward_data.task002_design import (
    audit_order_window, cutoff_diagnostics, fixed_hf_angle_pilot, lf_angle_pilot,
)
from src.forward_data.task002_schema import (
    TASK002_OBSERVABLE_SCHEMA_VERSION, Task002ForwardParameters,
    classify_task002_request, task002_parameter_catalog,
)


LF = "S_LF_HYBRID_P4_H10_M120"
HF = "S_HF_HYBRID_P6_H10_M120"


def _parameters(**updates) -> Task002ForwardParameters:
    values = dict(
        height_nm=120.0, width_x_nm=17.0, grazing_deg=5.25,
        azimuth_deg=45.0, model_id=LF,
    )
    values.update(updates)
    return Task002ForwardParameters(**values)


def test_s_only_schema_and_exact_zero_fail_closed() -> None:
    catalog = task002_parameter_catalog()
    assert catalog["fixed"] == {"wavelength_nm": 13.5, "incident_polarization": "S"}
    assert classify_task002_request({
        "height_nm": 120, "width_x_nm": 17, "grazing_deg": 0,
        "azimuth_deg": 45,
    })["status"] == "zero_grazing_limit_not_defined"
    assert classify_task002_request({
        "height_nm": 120, "width_x_nm": 17, "grazing_deg": 0.1,
        "azimuth_deg": 45,
    })["status"] == "out_of_training_domain"
    assert classify_task002_request({
        "height_nm": 120, "width_x_nm": 17, "grazing_deg": 5,
        "azimuth_deg": 45, "incident_polarization": "P",
    })["status"] == "polarization_not_trained"
    with pytest.raises(ValueError, match="polarization_not_trained"):
        _parameters(incident_polarization="P").validate()


@pytest.mark.parametrize("grazing,azimuth", [(0.5, 0.0), (5.25, 45.0), (10.0, 90.0)])
def test_angle_conversion_and_normalized_wavevector(grazing: float, azimuth: float) -> None:
    parameters = _parameters(grazing_deg=grazing, azimuth_deg=azimuth)
    assert parameters.theta_deg == pytest.approx(90.0 - grazing)
    features = parameters.normalized_features()
    assert features.shape == (4,)
    assert features[2] ** 2 + features[3] ** 2 == pytest.approx(
        np.cos(np.deg2rad(grazing)) ** 2
    )


def test_lf_and_hf_angle_pilot_are_frozen_and_unique() -> None:
    lf = lf_angle_pilot()
    hf = fixed_hf_angle_pilot()
    assert len(lf) == len({row["angle_id"] for row in lf}) == 49
    assert len(hf) == len({row["angle_id"] for row in hf}) == 9
    assert {row["role"] for row in hf} == {"corner", "edge_midpoint", "center"}


def test_order_window_and_cutoff_audit() -> None:
    audit = audit_order_window()
    assert audit["coverage_pass"] is True
    assert audit["missing_propagating_m"] == []
    assert set(audit["propagating_m_union"]).issubset(FIXED_M_ORDERS)
    cutoff = cutoff_diagnostics(_parameters(grazing_deg=0.5, azimuth_deg=0.0))
    assert cutoff["cutoff_metric"] >= 0.0
    assert len(cutoff["orders"]) == len(FIXED_M_ORDERS)


def test_task002_command_reuses_exact_qualified_s_route(tmp_path: Path) -> None:
    command = task002_hybrid_command(
        _parameters(model_id=HF), root=tmp_path, baseline_sha="a" * 40,
        output_record=tmp_path / "record.json", memory_stages=tmp_path / "stages.jsonl",
    )
    parsed = _parse_args(command[command.index("benchmarks.run_task032_phase6_augmented") + 1:])
    assert parsed.task001_surrogate_pilot_gate is True
    assert parsed.task001_model_id == "HF10"
    assert parsed.polarization_kind == "s"
    assert parsed.degree == 6 and parsed.requested_modes == 120


def test_campaign_cli_requires_one_explicit_sample(tmp_path: Path) -> None:
    args = _parser().parse_args([
        "run-one", "--root", str(tmp_path), "--baseline-sha", "a" * 40,
        "--artifact-root", str(tmp_path / "artifacts"),
        "--campaign-manifest", str(tmp_path / "campaign.json"),
        "--model-id", LF, "--height-nm", "120", "--width-x-nm", "17",
        "--grazing-deg", "0.5", "--azimuth-deg", "90",
    ])
    assert args.command == "run-one" and args.grazing_deg == 0.5


def test_campaign_dedup_resume_and_completed_immutability(tmp_path: Path) -> None:
    manifest_path = tmp_path / "campaign.json"
    parameters = _parameters()
    update_manifest(
        manifest_path, baseline_sha="a" * 40, parameters=parameters,
        status="reserved", run_directory=tmp_path / "run",
    )
    update_manifest(
        manifest_path, baseline_sha="a" * 40, parameters=parameters,
        status="measured_pass", run_directory=tmp_path / "run",
    )
    manifest = load_manifest(manifest_path, baseline_sha="a" * 40)
    assert list(manifest["samples"]) == [sample_key(parameters)]
    with pytest.raises(ValueError, match="immutable"):
        update_manifest(
            manifest_path, baseline_sha="a" * 40, parameters=parameters,
            status="reserved",
        )
    with pytest.raises(ValueError, match="baseline"):
        load_manifest(manifest_path, baseline_sha="b" * 40)


def _mother_response() -> dict:
    orders = []
    for side in ("reflection", "transmission"):
        for m in FIXED_M_ORDERS:
            carrying = m != 1
            orders.append({
                "side": side, "port_side": "top" if side == "reflection" else "bottom",
                "m": m, "n": 0, "kx": {"re": 0.0, "im": 0.0},
                "ky": {"re": 0.0, "im": 0.0}, "kz": {"re": 1.0, "im": 0.0},
                "dispersion_propagating": carrying, "power_carrying": carrying,
                "components": {
                    pol: {
                        "amplitude_re": 0.1 if carrying else None,
                        "amplitude_im": 0.0 if carrying else None,
                        "power": 0.01 if carrying else None,
                        "power_carrying": carrying,
                    } for pol in ("s", "p")
                },
                "order_total_power": 0.02 if carrying else None,
            })
    return {"schema_version": TASK002_OBSERVABLE_SCHEMA_VERSION, "orders": orders}


def test_dataset_roundtrip_hash_split_and_structural_null(tmp_path: Path) -> None:
    samples = []
    for index, split in enumerate(("train_lf", "train_hf", "frozen_validation")):
        samples.append({
            "sample_id": f"s{index}", "source_sha": "c" * 40, "source_dirty": False,
            "status": "measured_pass", "split": split,
            "inputs": [120.0, 17.0, 5.25, 45.0],
            "aggregates": {"R_total": 0.1, "T_total": 0.6, "A_balance": 0.3, "A_volume": 0.3},
            "mother_response": _mother_response(),
        })
    dataset_dir = tmp_path / "dataset"
    result = write_compact_dataset(samples, output_dir=dataset_dir, dataset_id="synthetic")
    assert result["status"] == "pass" and result["sample_count"] == 3
    powers = np.load(dataset_dir / "order_powers.npy", allow_pickle=False)
    mask = np.load(dataset_dir / "power_carrying_mask.npy", allow_pickle=False)
    assert np.array_equal(np.isnan(powers), ~mask)
    assert verify_compact_dataset(dataset_dir) == result
    with (dataset_dir / "sample_records.jsonl").open("a") as stream:
        stream.write("tamper\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_compact_dataset(dataset_dir)


def test_case112_scaffold_contract() -> None:
    record = build_scaffold_record()
    assert all(record["gates"].values())
