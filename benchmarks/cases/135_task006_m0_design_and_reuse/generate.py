"""Generate Task006 M0 frozen design manifests without launching FEM."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from surrogate.task006.design import (  # noqa: E402
    ANGLES,
    BLIND_GEOMETRIES,
    FORWARD_SOLVER_SHA,
    MODEL_ID,
    OBSERVABLE_SCHEMA,
    ROUTE_ID,
    TASK006_DATASET_ID,
    TASK005_LOCK,
    TRAIN_GEOMETRIES,
    canonical_hash,
    design_payload,
    file_hash,
    blind_payload,
    reuse_payload,
    training_payload,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    outcomes = ROOT / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes"
    outcomes.mkdir(parents=True, exist_ok=True)
    lock_path = ROOT / TASK005_LOCK
    channel_path = ROOT / "benchmarks/artifacts/cases/132_task005_sensitivity_dataset/derived_contract_v1/channel_contracts.json"
    recovery_path = ROOT / "surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/outcomes/OFF_CENTRE_RECOVERY.json"
    channel_contract = json.loads(channel_path.read_text())
    robust = channel_contract["contracts"]["M1_order_total_robust"]["per_angle"]
    fixed_contract = {
        "schema_version": "task006.fixed-illumination-contract.v1",
        "status": "frozen",
        "dataset_id": "task006_fixed_A05_A07_A09_hw_train37_p5_ny4_v1",
        "forward_solver_sha": FORWARD_SOLVER_SHA,
        "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID,
        "observable_schema_version": OBSERVABLE_SCHEMA,
        "wavelength_nm": 13.5,
        "polarization": "S",
        "mesh": [6, 4, 14],
        "mumps_icntl_14": 40,
        "mpi_ranks": 2,
        "threads_per_rank": 1,
        "angles": [
            {"angle_id": aid, "grazing_deg": g, "azimuth_deg": a,
             "axis_position": i, "channel_identity": robust[aid]["channels"],
             "channel_tier": robust[aid]["tier"], "channel_threshold": robust[aid]["count"] and 1e-3}
            for i, (aid, g, a) in enumerate(ANGLES)
        ],
        "s0_contract": {"targets": ["R_total", "T_total", "A_balance"],
                        "latent": "zR=log((R+eps)/(A+eps)); zT=log((T+eps)/(A+eps)); softmax(zR,zT,0)"},
        "s1_contract": {
            "source": "Task005 M1_order_total_robust",
            "side_totals": ["reflection", "transmission"],
            "other_definition": "side_total - sum(selected frozen channels)",
            "no_zero_fill": True,
            "failure_if_mask_false_nonfinite_or_ledger_failure": True,
        },
        "task005_v2_lock": {"path": str(lock_path.relative_to(ROOT)), "sha256": _sha(lock_path)},
        "task005_channel_contract": {"path": str(channel_path.relative_to(ROOT)), "sha256": _sha(channel_path)},
        "task005_m4_recovery_evidence": {"path": str(recovery_path.relative_to(ROOT)), "sha256": _sha(recovery_path)},
        "frozen_angle_order": [aid for aid, _, _ in ANGLES],
        "validation_target_accessed": False,
        "blind_response_accessed": False,
    }
    (outcomes / "FIXED_ILLUMINATION_CONTRACT.json").write_text(
        json.dumps(fixed_contract, indent=2, ensure_ascii=False) + "\n"
    )
    mother = design_payload(ROOT)
    training = training_payload(ROOT)
    blind = blind_payload()
    reuse = reuse_payload(ROOT)
    (outcomes / "HW_MOTHER_GRID.json").write_text(json.dumps(mother, indent=2, ensure_ascii=False) + "\n")
    (outcomes / "HW_TRAIN37_DESIGN.json").write_text(json.dumps(training, indent=2, ensure_ascii=False) + "\n")
    (outcomes / "HW_BLIND12_DESIGN.json").write_text(json.dumps(blind, indent=2, ensure_ascii=False) + "\n")
    (outcomes / "HW_REUSE_INVENTORY.json").write_text(json.dumps(reuse, indent=2, ensure_ascii=False) + "\n")
    result = {
        "schema_version": "task006.case135-m0-generation.v1",
        "status": "pass",
        "new_fem_count": 0,
        "blind_response_accessed": False,
        "outputs": {name: _sha(outcomes / name) for name in (
            "FIXED_ILLUMINATION_CONTRACT.json", "HW_MOTHER_GRID.json",
            "HW_TRAIN37_DESIGN.json", "HW_BLIND12_DESIGN.json",
            "HW_REUSE_INVENTORY.json")},
    }
    (ROOT / "benchmarks/cases/135_task006_m0_design_and_reuse/records").mkdir(parents=True, exist_ok=True)
    (ROOT / "benchmarks/cases/135_task006_m0_design_and_reuse/records/case135_generation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
