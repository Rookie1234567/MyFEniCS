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
from .features import DOMAIN, transform_features
from .physics import analytic_power_mask
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
        "schema_version": "task003.feature-contract.v1",
        "public_inputs": ["height_nm", "width_x_nm", "grazing_deg", "azimuth_deg"],
        "internal_features": ["height_scaled", "width_scaled", "kx_over_k0", "ky_over_k0"],
        "height_scaling": {"center_nm": 120.0, "half_range_nm": 5.0, "output": "[-1,1]"},
        "width_scaling": {"center_nm": 17.0, "half_range_nm": 1.0, "output": "[-1,1]"},
        "wavevector": {"kx_over_k0": "cos(grazing)*cos(azimuth)",
                        "ky_over_k0": "cos(grazing)*sin(azimuth)"},
        "domain": DOMAIN,
        "zero_grazing": "fail_closed",
        "statistics_source": "training rows only; no validation access",
    }


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
    analytic = analytic_power_mask(dataset.inputs)
    analytic_match = bool(np.array_equal(analytic, dataset.power_carrying_mask))
    if not analytic_match:
        raise RuntimeError("analytic propagation mask disagrees with training data")
    cv = run_training_cv()
    _dump(OUT / "FEATURE_CONTRACT.json", feature_contract)
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
    status = {
        "task": "Task003",
        "status": "controlled_stop_before_model_lock" if cv["status"] != "pass" else "cv_gate_pass",
        "source_sha": _head(),
        "dataset_verification": verification.as_dict(),
        "analytic_mask_match": analytic_match,
        "training_cv_hard_gate": cv["status"] == "pass",
        "model_selection_lock": "not_created_hard_cv_gate_failed",
        "frozen_validation": "sealed_not_accessed",
        "active_learning": cv["active_learning"],
        "prohibited_work": {"fem_rerun": False, "angle_doe": False, "inversion": False,
                            "validation_target_read": False},
    }
    _dump(OUT / "TRAINING_STAGE_STATUS.json", status)
    return status
