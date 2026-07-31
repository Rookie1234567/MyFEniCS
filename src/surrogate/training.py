"""Task003 train-only orchestration and evidence writer.

The command intentionally stops before model locking when the hard training CV
Gate is not met.  It never opens frozen-validation targets in that state.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from .cv import run_training_cv
from .dataset import CASE119_ROOT, load_training_dataset, verify_case119_dataset
from .features import (DOMAIN, FEATURE_CONTRACT_VERSION, FROZEN_FEATURE_CANDIDATE,
                       feature_contracts, transform_features)
from .physics import power_mask_authority
from .targets import aggregate_contract, channel_table, power_contract


TASK_ROOT = Path("surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training")
OUT = TASK_ROOT / "outcomes"
CASE_ROOT = Path("benchmarks/cases/120_task003_surrogate_training")


def _dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def _head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _feature_contract() -> dict[str, Any]:
    return {
        "schema_version": FEATURE_CONTRACT_VERSION,
        "public_inputs": ["height_nm", "width_x_nm", "grazing_deg", "azimuth_deg"],
        "frozen_candidate": FROZEN_FEATURE_CANDIDATE,
        "internal_features": ["height_scaled", "width_scaled", "grazing_scaled", "azimuth_scaled"],
        "height_scaling": {"center_nm": 120.0, "half_range_nm": 5.0, "output": "[-1,1]"},
        "width_scaling": {"center_nm": 17.0, "half_range_nm": 1.0, "output": "[-1,1]"},
        "wavevector": {"kx_over_k0": "cos(grazing)*cos(azimuth)",
                        "ky_over_k0": "cos(grazing)*sin(azimuth)"},
        "candidate_sets": feature_contracts(),
        "comparison_only_candidates": ["A", "C"],
        "domain": DOMAIN,
        "zero_grazing": "fail_closed",
        "statistics_source": "training rows only; no validation access",
    }


def _load_design_points(path: Path) -> np.ndarray:
    design = json.loads(path.read_text(encoding="utf-8"))
    return np.asarray([[float(row[k]) for k in
                        ("height_nm", "width_x_nm", "grazing_deg", "azimuth_deg")]
                       for row in design["points"]], dtype=np.float64)


def _mask_authority(dataset: Any) -> dict[str, Any]:
    """Write independent side masks using inputs/design metadata only."""
    OUT.mkdir(parents=True, exist_ok=True)
    train = np.asarray(dataset.inputs, dtype=np.float64)
    validation = _load_design_points(
        Path("benchmarks/cases/116_task002_single_fidelity_design/frozen_validation_design.json"))
    candidate = _load_design_points(
        Path("benchmarks/cases/116_task002_single_fidelity_design/candidate_pool.json"))
    result = {
        "training": power_mask_authority(train),
        "frozen_validation_inputs_only": power_mask_authority(validation),
        "candidate_pool": power_mask_authority(candidate),
    }
    arrays_path = OUT / "power_mask_authority.npz"
    np.savez_compressed(arrays_path, **{
        f"{split}_power": value["power_carrying"]
        for split, value in result.items()
    }, **{
        f"{split}_dispersion": value["dispersion_propagating"]
        for split, value in result.items()
    })
    def digest(array: np.ndarray) -> str:
        import hashlib
        return hashlib.sha256(np.ascontiguousarray(array).astype(np.uint8).tobytes()).hexdigest()
    summary = {
        "schema_version": "task003.power-mask-authority.v2",
        "authority": "src.common.modes_3d outgoing port mode Poynting identity",
        "sides": {"reflection": "top/air", "transmission": "bottom/complex_substrate"},
        "m_values": list(range(-7, 4)), "components": ["s", "p"],
        "dispersion_propagating_and_power_carrying_are_distinct": True,
        "validation_target_accessed": False,
        "arrays_file": str(arrays_path),
        "splits": {
            split: {
                "shape": list(value["power_carrying"].shape),
                "power_sha256": digest(value["power_carrying"]),
                "dispersion_sha256": digest(value["dispersion_propagating"]),
                "power_active_count": int(value["power_carrying"].sum()),
                "dispersion_active_count": int(value["dispersion_propagating"].sum()),
            } for split, value in result.items()
        },
    }
    _dump(OUT / "POWER_MASK_AUTHORITY.json", summary)
    return summary


def _audit_markdown(dataset: Any, channels: list[Any]) -> str:
    x = dataset.inputs
    p = dataset.order_powers
    mask = dataset.power_carrying_mask
    lines = [
        "# Task003 training-only data audit",
        "",
        "`dataset_id=task002_m4e_p5_ny4_112_v3`; only the 96 training rows were",
        "materialized. Frozen-validation targets were not opened.",
        "",
        "## Input coverage",
        "",
        f"- shape = {list(x.shape)}; ranges = min `{x.min(0).tolist()}`, max `{x.max(0).tolist()}`",
        f"- unique counts by input = {[int(len(np.unique(x[:, i]))) for i in range(4)]}",
        "- feature map is fixed to scaled height/width and in-plane wavevector components.",
        "",
        "## Aggregate ranges",
    ]
    for i, name in enumerate(("R_total", "T_total", "A_balance", "A_volume")):
        lines.append(f"- `{name}`: min={dataset.aggregates[:, i].min():.8g}, "
                     f"max={dataset.aggregates[:, i].max():.8g}, "
                     f"p50={np.percentile(dataset.aggregates[:, i], 50):.8g}")
    lines.extend(["", "## Structural null and powers", "",
                  f"- power tensor shape = {list(p.shape)}; active entries = {int(mask.sum())} / {mask.size}",
                  f"- selected primary channels (training max >= 1e-6) = {len(channels)}",
                  "- false mask entries remain NaN/null and are never zero-filled into a loss.",
                  "- analytic propagation mask matches all 96 training rows for every fixed order.",
                  "", "## Boundary observations", "",
                  "The training design contains sparse exact corner and cutoff anchors. The",
                  "deterministic five-fold CV therefore reports their region metrics separately;",
                  "no point was deleted or relabelled to improve a Gate."])
    return "\n".join(lines) + "\n"


def run_training_stage() -> dict[str, Any]:
    verification = verify_case119_dataset(CASE119_ROOT)
    dataset = load_training_dataset(CASE119_ROOT)
    feature_contract = _feature_contract()
    target_contract = {"aggregate": aggregate_contract(), "power": power_contract()}
    identity = json.loads((CASE119_ROOT / "order_identity.json").read_text())
    channels = channel_table(identity, dataset.order_powers, dataset.power_carrying_mask)
    authority = _mask_authority(dataset)
    analytic = power_mask_authority(dataset.inputs)["power_carrying"]
    analytic_match = bool(np.array_equal(analytic, dataset.power_carrying_mask))
    if not analytic_match:
        raise RuntimeError("analytic propagation mask disagrees with training data")
    cv = run_training_cv()
    oof_records = cv.pop("oof_records", [])
    cv["oof_record_count"] = len(oof_records)
    _dump(OUT / "FEATURE_CONTRACT.json", feature_contract)
    _dump(OUT / "FEATURE_CONTRACT_v2.json", feature_contract)
    _dump(OUT / "TARGET_CONTRACT.json", target_contract)
    _dump(OUT / "CHANNEL_IDENTITY.json", {
        "schema_version": "task003.channel-identity.v1",
        "observable_schema": "task002.fixed-n0-orders.v3",
        "order_axis": identity["axis"],
        "component_axis": identity["component_axis"],
        "primary_threshold": 1.0e-6,
        "primary_channels": [channel.__dict__ | {"key": channel.key()} for channel in channels],
    })
    (OUT / "TRAINING_ONLY_DATA_AUDIT.md").write_text(_audit_markdown(dataset, channels))
    _dump(OUT / "training_cv.json", cv)
    _dump(OUT / "training_cv_oof.json", {
        "schema_version": "task003.training-oof.v2",
        "dataset_id": dataset.dataset_id,
        "training_count": dataset.n_samples,
        "selected_candidate": cv["selected_candidate"],
        "records": oof_records,
    })
    status = {
        "task": "Task003",
        "status": "controlled_stop_before_model_lock" if cv["status"] != "pass" else "cv_gate_pass",
        "source_sha": _head(),
        "dataset_verification": verification.as_dict(),
        "analytic_mask_match": analytic_match,
        "training_cv_hard_gate": cv["status"] == "pass",
        "selected_candidate": cv["selected_candidate"],
        "selected_feature_candidate": cv["selected_feature_candidate"],
        "uncertainty_diagnostics": cv["uncertainty_diagnostics"],
        "oof_record_count": cv["oof_record_count"],
        "model_selection_lock": "not_created_hard_cv_gate_failed",
        "frozen_validation": "sealed_not_accessed",
        "active_learning": cv["active_learning"],
        "prohibited_work": {"fem_rerun": False, "angle_doe": False, "inversion": False,
                            "validation_target_read": False},
    }
    _dump(OUT / "TRAINING_STAGE_STATUS.json", status)
    return status
