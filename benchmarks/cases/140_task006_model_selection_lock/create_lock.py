"""Create the Task006 model lock after M2R and Case139 pass."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from surrogate.task006.design import (  # noqa: E402
    ANGLES,
    BLIND_GEOMETRIES,
    FORWARD_SOLVER_SHA,
    MODEL_ID,
    OBSERVABLE_SCHEMA,
    ROUTE_ID,
    TASK005_LOCK,
    TASK006_DATASET_ID,
    canonical_hash,
    file_hash,
)
from surrogate.task006.m2r import _fit_contract  # noqa: E402
from surrogate.task006.dataset import load_dataset  # noqa: E402


OUTCOMES = ROOT / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes"
DATASET_ROOT = ROOT / "benchmarks/artifacts/cases/137_task006_train37_dataset/train37"
LOCK_PATH = OUTCOMES / "TASK006_MODEL_SELECTION_LOCK.json"


def _model_payload(model: Any) -> dict[str, Any]:
    """Serialize lightweight fitted metadata and coefficients for lock audit."""

    payload = {"class": type(model).__name__, "metadata": model.metadata()}
    if hasattr(model, "coefficients"):
        payload["coefficients"] = np.asarray(model.coefficients, dtype=np.float64).tolist()
        payload["basis_indices"] = [list(item) for item in (model._indices or [])]
    if hasattr(model, "x_train") and model.x_train is not None:
        payload["x_train_hash"] = canonical_hash(np.asarray(model.x_train).tolist())
        payload["y_train_hash"] = canonical_hash(np.asarray(model.y_train).tolist())
    return payload


def main() -> int:
    case139 = ROOT / "benchmarks/cases/139_task006_m2r_contract_replay/records/case139_check.json"
    replay = json.loads(case139.read_text())
    if replay.get("status") != "pass":
        raise SystemExit("Case139 must pass before creating the model lock")
    comparison = json.loads((OUTCOMES / "TRAIN37_MODEL_COMPARISON_V2.json").read_text())
    selection = json.loads((OUTCOMES / "TRAINING_MODEL_SELECTION_CANDIDATE_V2.json").read_text())
    recovery = json.loads((OUTCOMES / "TRAIN37_SYNTHETIC_RECOVERY_V2.json").read_text())
    folds = json.loads((OUTCOMES / "TRAIN37_GEOMETRY_FOLDS.json").read_text())
    blind_design = json.loads((OUTCOMES / "HW_BLIND12_DESIGN.json").read_text())
    if selection.get("status") != "m2r_training_qualified_pending_lock":
        raise SystemExit("M2R training Gate did not qualify a lock")
    selected = selection["selected_candidate"]
    selected_result = comparison["candidates"][selected]
    if not selected_result.get("hard_gate") or not recovery.get("hard_gate"):
        raise SystemExit("selected candidate or synthetic recovery Gate failed")
    data = load_dataset(DATASET_ROOT)
    geometry = np.asarray(data["geometries"], dtype=np.float64)
    latent = np.asarray(data["aggregate_latent"], dtype=np.float64)
    fractions = np.asarray(data["s1_fractions"], dtype=np.float64)
    full_train = np.arange(len(geometry), dtype=np.int64)
    full_fit = _fit_contract(selected, geometry, latent, fractions, full_train,
                             geometry, seed=1200)
    production_models = []
    for contract, models in (("S0", full_fit["_models"]["aggregate"]),
                             ("S1_fraction_logit", full_fit["_models"]["fraction"])):
        for index, model in enumerate(models):
            production_models.append({"contract": contract, "scalar_index": index,
                                      "model": _model_payload(model)})
    manifest = json.loads((DATASET_ROOT / "dataset_manifest.json").read_text())
    lock = {
        "schema_version": "task006.model-selection-lock.v1",
        "status": "locked_for_blind",
        "dataset_id": TASK006_DATASET_ID,
        "dataset_manifest_sha256": file_hash(DATASET_ROOT / "dataset_manifest.json"),
        "dataset_file_hashes": manifest.get("file_hashes", {}),
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
        "fixed_angle_order": [angle_id for angle_id, _, _ in ANGLES],
        "fixed_angle_tuples": [[grazing, azimuth] for _, grazing, azimuth in ANGLES],
        "s0_contract": {
            "targets": ["R_total", "T_total", "A_balance"],
            "latent": "zR=log((R+eps)/(A+eps)); zT=log((T+eps)/(A+eps)); softmax(zR,zT,0)",
            "epsilon": 1.0e-15,
            "side_total_authority": "S0 predicted R_total/T_total",
        },
        "s1_contract": {
            "selected_channels": [["reflection", 0, 0], ["transmission", 0, 0]],
            "selected_fraction_transform": "log((selected+eps)/(other+eps)) then sigmoid",
            "other_semantics": "S0 predicted side total * (1-selected_fraction)",
            "no_independent_side_total_model": True,
            "actual_ledger_gate": "max_abs(selected+other-S0_side_total)<=1e-12",
        },
        "selected_candidate": selected,
        "selection_basis": selection["selection_basis"],
        "selection_scores": comparison["candidates"],
        "production_fitted_model_metadata": production_models,
        "geometry_folds": {
            "path": "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes/TRAIN37_GEOMETRY_FOLDS.json",
            "sha256": file_hash(OUTCOMES / "TRAIN37_GEOMETRY_FOLDS.json"),
            "folds_sha256": folds["folds_sha256"],
        },
        "training_evidence": {
            "comparison_path": "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes/TRAIN37_MODEL_COMPARISON_V2.json",
            "comparison_sha256": file_hash(OUTCOMES / "TRAIN37_MODEL_COMPARISON_V2.json"),
            "oof_path": "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes/TRAIN37_OOF_PREDICTIONS_V2.json",
            "oof_sha256": file_hash(OUTCOMES / "TRAIN37_OOF_PREDICTIONS_V2.json"),
            "ledger_path": "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes/TRAIN37_S1_LEDGER_V2.json",
            "ledger_sha256": file_hash(OUTCOMES / "TRAIN37_S1_LEDGER_V2.json"),
            "uncertainty_path": "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes/TRAIN37_UNCERTAINTY_V2.json",
            "uncertainty_sha256": file_hash(OUTCOMES / "TRAIN37_UNCERTAINTY_V2.json"),
            "synthetic_recovery_path": "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes/TRAIN37_SYNTHETIC_RECOVERY_V2.json",
            "synthetic_recovery_sha256": file_hash(OUTCOMES / "TRAIN37_SYNTHETIC_RECOVERY_V2.json"),
            "selected_prediction_hash": selection["selected_prediction_hash"],
            "uncertainty": selected_result["uncertainty"],
            "s0_metrics": selected_result["s0_metrics"],
            "s1_metrics": selected_result["s1_metrics"],
            "s0_region_metrics": selected_result["s0_region_metrics"],
            "s1_region_metrics": selected_result["s1_region_metrics"],
            "synthetic_recovery_summary": recovery["summary"],
            "case139_path": "benchmarks/cases/139_task006_m2r_contract_replay/records/case139_check.json",
            "case139_sha256": file_hash(case139),
        },
        "blind_design": {
            "path": "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes/HW_BLIND12_DESIGN.json",
            "sha256": file_hash(OUTCOMES / "HW_BLIND12_DESIGN.json"),
            "count": blind_design["count"],
            "geometries": blind_design["geometries"],
            "tuple_sha256": blind_design["tuple_sha256"],
            "fixed_angle_order": [angle_id for angle_id, _, _ in ANGLES],
            "fem_count": 36,
        },
        "train37_geometry_count": 37,
        "blind_response_accessed": False,
        "validation_target_accessed": False,
        "blind_fem_run": False,
        "model_selection_locked_before_blind": True,
    }
    LOCK_PATH.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": lock["status"], "selected_candidate": selected,
                      "lock_path": str(LOCK_PATH), "blind_fem_run": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
