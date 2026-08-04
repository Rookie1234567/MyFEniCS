"""Independent checker for the Task005 16-angle sensitivity package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
DATASET_ID = "task005_discrete_angle_hw_sensitivity_p5_ny4_v1"
ANGLES = (
    ("A00", 0.5, 0.0), ("A01", 0.5, 45.0), ("A02", 0.5, 90.0),
    ("A03", 1.0, 15.0), ("A04", 1.0, 60.0),
    ("A05", 2.0, 0.0), ("A06", 2.0, 45.0), ("A07", 2.0, 90.0),
    ("A08", 4.0, 15.0), ("A09", 4.0, 60.0), ("A10", 4.0, 90.0),
    ("A11", 6.0, 30.0), ("A12", 6.0, 75.0),
    ("A13", 8.0, 45.0), ("A14", 10.0, 0.0), ("A15", 10.0, 90.0),
)
STATES = ("H-", "H+", "W-", "W+")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _array(dataset: Path, name: str) -> np.ndarray:
    return np.load(dataset / name, allow_pickle=False)


def check(dataset: Path, campaign_path: Path) -> tuple[dict[str, bool], list[str]]:
    checks: dict[str, bool] = {}
    errors: list[str] = []
    manifest_path = dataset / "dataset_manifest.json"
    required = [manifest_path, dataset / "derivatives.json", dataset / "order_identity.json",
                dataset / "record_identity.json"] + [dataset / name for name in (
                    "angles.npy", "nominal_inputs.npy", "nominal_aggregates.npy",
                    "perturbed_aggregates.npy", "nominal_order_powers.npy",
                    "perturbed_order_powers.npy", "nominal_order_mask.npy",
                    "perturbed_order_mask.npy")]
    checks["required_files"] = all(path.is_file() for path in required)
    if not checks["required_files"]:
        return checks, ["required dataset file missing"]
    manifest = json.loads(manifest_path.read_text())
    arrays = {name: _array(dataset, name) for name in (
        "angles.npy", "nominal_inputs.npy", "nominal_aggregates.npy",
        "perturbed_aggregates.npy", "nominal_order_powers.npy",
        "perturbed_order_powers.npy", "nominal_order_mask.npy",
        "perturbed_order_mask.npy")}
    expected_shapes = {
        "angles.npy": ((16, 2), "float64"), "nominal_inputs.npy": ((16, 4), "float64"),
        "nominal_aggregates.npy": ((16, 4), "float64"),
        "perturbed_aggregates.npy": ((16, 4, 4), "float64"),
        "nominal_order_powers.npy": ((16, 22), "float64"),
        "perturbed_order_powers.npy": ((16, 4, 22), "float64"),
        "nominal_order_mask.npy": ((16, 22), "bool"),
        "perturbed_order_mask.npy": ((16, 4, 22), "bool"),
    }
    checks["array_identity"] = all(arrays[name].shape == shape and str(arrays[name].dtype) == dtype
                                    for name, (shape, dtype) in expected_shapes.items())
    checks["manifest_identity"] = bool(
        manifest.get("schema_version") == "task005.discrete-sensitivity-dataset.v1"
        and manifest.get("dataset_id") == DATASET_ID
        and manifest.get("status") == "immutable"
        and manifest.get("forward_solver_sha") == FORWARD_SHA
        and manifest.get("model_id") == MODEL_ID and manifest.get("solver_route_id") == ROUTE_ID
        and manifest.get("angle_count") == 16 and manifest.get("state_count_per_angle") == 4
        and manifest.get("new_fem_count") == 44 and manifest.get("m1_reused_count") == 20
        and manifest.get("validation_target_accessed") is False
        and manifest.get("formal_inversion") is False
        and manifest.get("step") == {"delta_h_nm": 1.25, "delta_w_nm": 0.25, "method": "central_difference"}
    )
    actual_hashes = {path.name: digest(path) for path in sorted(dataset.iterdir())
                     if path.is_file() and path.name != "dataset_manifest.json"}
    checks["package_hashes"] = actual_hashes == manifest.get("file_hashes")
    angle_rows = arrays["angles.npy"].tolist()
    expected_angles = [[g, a] for _, g, a in ANGLES]
    checks["exact_angle_identity"] = bool(
        angle_rows == expected_angles
        and manifest.get("angle_tuple_sha256") == canonical(expected_angles)
        and arrays["nominal_inputs.npy"].tolist() == [[120.0, 17.0, g, a] for _, g, a in ANGLES]
    )
    nominal = arrays["nominal_aggregates.npy"]
    perturbed = arrays["perturbed_aggregates.npy"]
    checks["aggregate_finite_difference_rebuild"] = bool(
        np.allclose((perturbed[:, 1, :2] - perturbed[:, 0, :2]) / 2.5,
                    np.asarray([row["contracts"]["M0_aggregate_RT"]["derivatives"]["h"]
                                for row in json.loads((dataset / "derivatives.json").read_text())]), rtol=0.0, atol=1e-13)
        and np.allclose((perturbed[:, 3, :2] - perturbed[:, 2, :2]) / 0.5,
                        np.asarray([row["contracts"]["M0_aggregate_RT"]["derivatives"]["w"]
                                    for row in json.loads((dataset / "derivatives.json").read_text())]), rtol=0.0, atol=1e-13)
    )
    derivatives = json.loads((dataset / "derivatives.json").read_text())
    checks["derivative_rows"] = bool(len(derivatives) == 16 and
                                      [row.get("angle_id") for row in derivatives] == [a[0] for a in ANGLES])
    order_checks = True
    for i, row in enumerate(derivatives):
        if row.get("grazing_deg") != ANGLES[i][1] or row.get("azimuth_deg") != ANGLES[i][2]:
            order_checks = False; continue
        for contract, threshold in (("M1_order_total_robust", 1.0e-3),
                                     ("M2_order_total_extended", 1.0e-5)):
            active = np.isfinite(arrays["nominal_order_powers.npy"][i])
            active &= np.isfinite(arrays["perturbed_order_powers.npy"][i]).all(axis=0)
            active &= np.max(np.abs(np.vstack((arrays["nominal_order_powers.npy"][i],
                                               arrays["perturbed_order_powers.npy"][i]))), axis=0) >= threshold
            expected_h = (arrays["perturbed_order_powers.npy"][i, 1, active]
                          - arrays["perturbed_order_powers.npy"][i, 0, active]) / 2.5
            expected_w = (arrays["perturbed_order_powers.npy"][i, 3, active]
                          - arrays["perturbed_order_powers.npy"][i, 2, active]) / 0.5
            actual = row["contracts"][contract]
            channels = [tuple(value) for value in actual["channels"]]
            axis = json.loads((dataset / "order_identity.json").read_text())["axis"]
            expected_channels = [tuple((x["side"], x["m"], x["n"])) for x in axis]
            expected_channels = [expected_channels[j] for j in np.flatnonzero(active)]
            order_checks &= channels == expected_channels
            order_checks &= np.allclose(expected_h, np.asarray(actual["derivatives"]["h"]), rtol=0.0, atol=1e-13)
            order_checks &= np.allclose(expected_w, np.asarray(actual["derivatives"]["w"]), rtol=0.0, atol=1e-13)
    checks["order_contract_rebuild"] = bool(order_checks)
    try:
        campaign = json.loads(campaign_path.read_text())
        checks["campaign_identity"] = bool(
            campaign.get("status") == "pass" and campaign.get("new_fem_count") == 44
            and campaign.get("reused_m1_count") == 20
            and campaign.get("validation_target_accessed") is False
            and len(campaign.get("records", {})) == 64
            and all(row.get("status") in {"measured_pass", "reused_m1"}
                    for row in campaign.get("records", {}).values())
        )
    except (OSError, ValueError, json.JSONDecodeError):
        checks["campaign_identity"] = False
    record_identity = json.loads((dataset / "record_identity.json").read_text())
    checks["record_source_identity"] = bool(
        len(record_identity) == 64
        and all(item.get("sample_path") and Path(item["sample_path"]).is_file()
                and item.get("status") in {"measured_pass", "reused_m1"}
                for item in record_identity.values())
    )
    if not all(checks.values()):
        errors.extend(f"failed:{key}" for key, value in checks.items() if not value)
    return checks, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("benchmarks/artifacts/cases/132_task005_sensitivity_dataset/dataset"))
    parser.add_argument("--campaign", type=Path, default=Path("surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/outcomes/M2_PRODUCTION_CAMPAIGN.json"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/cases/132_task005_sensitivity_dataset/records/case132_check.json"))
    args = parser.parse_args()
    checks, errors = check(args.dataset.resolve(), args.campaign.resolve())
    result = {"schema_version": "task005.case132-check.v1", "status": "pass" if all(checks.values()) else "failed", "checks": checks, "errors": errors, "new_fem_count": 44, "validation_target_accessed": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
