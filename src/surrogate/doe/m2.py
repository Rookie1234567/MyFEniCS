"""Task005 M2 16-angle production campaign and compact sensitivity dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time
from typing import Any

import numpy as np

from .design import (
    ANGLE_CANDIDATES, AUDIT_ANGLE_IDS, FORWARD_SOLVER_SHA, H0, W0,
    MODEL_ID, ROUTE_ID, OBSERVABLE_SCHEMA, canonical_hash,
)
from .runner import (
    CASE_ID, SURROGATE_ROOT, FORWARD_ROOT, STATES, STEPS, _command,
    _load_nominal_records, _run_with_heartbeat, _state_geometry,
)
from .sensitivity import (
    build_production_derivatives, record_observables, write_json,
)


DATASET_ID = "task005_discrete_angle_hw_sensitivity_p5_ny4_v1"
CASE_ID_M2 = "task005_m2_production_v1"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def _load_design(outcomes_dir: Path) -> dict[str, Any]:
    design = json.loads((outcomes_dir / "DISCRETE_ANGLE_DESIGN.json").read_text())
    lock = json.loads((outcomes_dir / "PRODUCTION_STEP_LOCK.json").read_text())
    if design.get("status") != "frozen" or design.get("new_fem_count") != 0:
        raise RuntimeError("M2 design is not frozen by M0")
    if lock.get("status") != "frozen" or lock.get("selected_steps") != {"h": "half", "w": "half"}:
        raise RuntimeError("M2 requires the passed half-step production lock")
    return {"design": design, "lock": lock}


def _load_m1_reuse(m1_manifest: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(m1_manifest.read_text())
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("records", {}).values():
        if row.get("angle_id") not in AUDIT_ANGLE_IDS or row.get("step") != "half":
            continue
        path = Path(row.get("sample_path", ""))
        if row.get("status") != "measured_pass" or not path.is_file():
            raise RuntimeError("M1 reuse row is not a measured sample")
        result[f"{row['angle_id']}/{row['state']}"] = {
            "sample_path": str(path.resolve()), "formal_record_sha256": row.get("formal_record_sha256"),
            "execution_sha256": row.get("execution_sha256"), "reuse": "M1_exact_record",
        }
    expected = {f"{angle}/{state}" for angle in AUDIT_ANGLE_IDS for state in STATES}
    if set(result) != expected:
        raise RuntimeError("M1 reuse does not contain all 20 half-step audit states")
    return result


def _expected_rows(artifact_root: Path, reuse: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    angle_map = {item[0]: (float(item[1]), float(item[2])) for item in ANGLE_CANDIDATES}
    index = 0
    for angle_id, grazing, azimuth in ANGLE_CANDIDATES:
        for state in STATES:
            h, w = _state_geometry("half", state)
            key = f"{angle_id}/{state}"
            if key in reuse:
                rows[key] = {
                    "key": key, "angle_id": angle_id, "state": state,
                    "design_index": index, "grazing_deg": grazing, "azimuth_deg": azimuth,
                    "height_nm": h, "width_nm": w,
                    "run_directory": str(Path(reuse[key]["sample_path"]).parent.resolve()),
                    "sample_path": reuse[key]["sample_path"], "formal_record_sha256": reuse[key]["formal_record_sha256"],
                    "execution_sha256": reuse[key]["execution_sha256"], "status": "reused_m1", "new_fem": False,
                }
            else:
                run = artifact_root / "m2" / angle_id / state
                rows[key] = {
                    "key": key, "angle_id": angle_id, "state": state,
                    "design_index": index, "grazing_deg": grazing, "azimuth_deg": azimuth,
                    "height_nm": h, "width_nm": w,
                    "run_directory": str(run.resolve()), "sample_path": None,
                    "formal_record_sha256": None, "execution_sha256": None,
                    "status": "reserved", "new_fem": True,
                }
            index += 1
    return rows


def _load_sample(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text())
    if value.get("status") != "measured_pass":
        raise RuntimeError(f"production sample is not measured_pass: {path}")
    if value.get("source_sha") != FORWARD_SOLVER_SHA or value.get("source_dirty") is not False:
        raise RuntimeError(f"production sample source identity mismatch: {path}")
    return value


def _save_arrays(dataset_dir: Path, nominal: list[dict[str, Any]],
                 states: dict[str, list[dict[str, Any]]], angle_ids: list[str]) -> dict[str, Any]:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    nominal_aggregates = np.asarray([[row["aggregates"][name] for name in
                                      ("R_total", "T_total", "A_balance", "A_volume")] for row in nominal], dtype=np.float64)
    perturbed_aggregates = np.asarray([
        [[row["aggregates"][name] for name in ("R_total", "T_total", "A_balance", "A_volume")]
         for row in states[angle_id]] for angle_id in angle_ids
    ], dtype=np.float64)
    nominal_order = np.full((len(nominal), 22), np.nan, dtype=np.float64)
    perturbed_order = np.full((len(nominal), 4, 22), np.nan, dtype=np.float64)
    nominal_mask = np.zeros((len(nominal), 22), dtype=bool)
    perturbed_mask = np.zeros((len(nominal), 4, 22), dtype=bool)
    order_identity = None
    for i, row in enumerate(nominal):
        value = record_observables(row)
        identity = value["order_identity"]
        if order_identity is None:
            order_identity = identity
        if identity != order_identity:
            raise RuntimeError("nominal order identity changed")
        nominal_order[i] = value["order_total"]
        nominal_mask[i] = np.isfinite(value["order_total"])
        for j, state in enumerate(states[angle_ids[i]]):
            current = record_observables(state)
            if current["order_identity"] != order_identity:
                raise RuntimeError("perturbed order identity changed")
            perturbed_order[i, j] = current["order_total"]
            perturbed_mask[i, j] = np.isfinite(current["order_total"])
    arrays = {
        "angles.npy": np.asarray([[row[1], row[2]] for row in ANGLE_CANDIDATES], dtype=np.float64),
        "nominal_inputs.npy": np.asarray([[H0, W0, row[1], row[2]] for row in ANGLE_CANDIDATES], dtype=np.float64),
        "nominal_aggregates.npy": nominal_aggregates,
        "perturbed_aggregates.npy": perturbed_aggregates,
        "nominal_order_powers.npy": nominal_order,
        "perturbed_order_powers.npy": perturbed_order,
        "nominal_order_mask.npy": nominal_mask,
        "perturbed_order_mask.npy": perturbed_mask,
    }
    for name, value in arrays.items():
        np.save(dataset_dir / name, value, allow_pickle=False)
    return {name: {"shape": list(value.shape), "dtype": str(value.dtype)}
            for name, value in arrays.items()}


def build_dataset(*, outcomes_dir: Path, train_dir: Path, dataset_dir: Path,
                  campaign: dict[str, Any]) -> dict[str, Any]:
    nominal_by_angle = _load_nominal_records(train_dir)
    angle_ids = [row[0] for row in ANGLE_CANDIDATES]
    state_records: dict[str, list[dict[str, Any]]] = {}
    state_payloads: dict[str, dict[str, Any]] = {}
    for angle_id in angle_ids:
        values = []
        for state in STATES:
            row = campaign["records"][f"{angle_id}/{state}"]
            sample = _load_sample(row["sample_path"])
            values.append(sample)
            state_payloads[f"{angle_id}/{state}"] = sample
        state_records[angle_id] = values
    array_identity = _save_arrays(dataset_dir, [nominal_by_angle[a] for a in angle_ids], state_records, angle_ids)
    derivatives: list[dict[str, Any]] = []
    for angle_id in angle_ids:
        derivatives.append({
            "angle_id": angle_id,
            "grazing_deg": float(next(row[1] for row in ANGLE_CANDIDATES if row[0] == angle_id)),
            "azimuth_deg": float(next(row[2] for row in ANGLE_CANDIDATES if row[0] == angle_id)),
            "nominal_sample_id": nominal_by_angle[angle_id]["sample_id"],
            "contracts": build_production_derivatives(
                nominal=nominal_by_angle[angle_id],
                states={state: state_payloads[f"{angle_id}/{state}"] for state in STATES},
                step="half",
            )["contracts"],
        })
    records_identity = {
        key: {
            "sample_path": str(Path(row["sample_path"]).resolve()),
            "formal_record_sha256": row.get("formal_record_sha256"),
            "execution_sha256": row.get("execution_sha256"),
            "status": row.get("status"), "new_fem": row.get("new_fem"),
        } for key, row in campaign["records"].items()
    }
    (dataset_dir / "derivatives.json").write_text(json.dumps(derivatives, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    (dataset_dir / "order_identity.json").write_text(json.dumps({
        "axis": [{"side": side, "m": m, "n": n} for side, m, n in record_observables(nominal_by_angle[angle_ids[0]])["order_identity"]]
    }, indent=2) + "\n")
    (dataset_dir / "record_identity.json").write_text(json.dumps(records_identity, indent=2, ensure_ascii=False) + "\n")
    # Exclude the manifest itself to avoid a circular self-hash.  This also
    # makes a resume rebuild deterministic after a prior manifest exists.
    file_hashes = {path.name: _digest(path) for path in sorted(dataset_dir.iterdir())
                   if path.is_file() and path.name != "dataset_manifest.json"}
    manifest = {
        "schema_version": "task005.discrete-sensitivity-dataset.v1",
        "dataset_id": DATASET_ID, "status": "immutable",
        "forward_solver_sha": FORWARD_SOLVER_SHA, "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID, "observable_schema_version": OBSERVABLE_SCHEMA,
        "fixed_geometry": {"height_nm": H0, "width_nm": W0, "wavelength_nm": 13.5, "polarization": "S"},
        "angle_count": 16, "state_count_per_angle": 4,
        "angle_tuple_sha256": canonical_hash([[row[1], row[2]] for row in ANGLE_CANDIDATES]),
        "design_sha256": _digest(outcomes_dir / "DISCRETE_ANGLE_DESIGN.json"),
        "production_step_lock_sha256": _digest(outcomes_dir / "PRODUCTION_STEP_LOCK.json"),
        "step": {"delta_h_nm": 1.25, "delta_w_nm": 0.25, "method": "central_difference"},
        "measurement_contracts": {
            "M0": "aggregate_RT=[R_total,T_total]; A audit only",
            "M1": "order_total_robust threshold 1e-3; active fixed-order total powers",
            "M2": "order_total_extended threshold 1e-5; absolute noise floor",
            "M3": "polarization-resolved diagnostic only",
        },
        "nominal_reuse": "immutable train112; no nominal FEM rerun",
        "new_fem_count": int(sum(1 for row in campaign["records"].values() if row.get("new_fem"))),
        "m1_reused_count": int(sum(1 for row in campaign["records"].values() if not row.get("new_fem"))),
        "validation_target_accessed": False, "formal_inversion": False,
        "arrays": array_identity, "file_hashes": file_hashes,
    }
    (dataset_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    # The manifest itself is outside the self-hash set so a checker can rebuild
    # the exact array/record package without circular hashing.
    return {"manifest": manifest, "derivatives": derivatives}


def run_m2(*, outcomes_dir: Path, train_dir: Path, artifact_root: Path,
           forward_root: Path = FORWARD_ROOT, timeout_seconds: float = 1800.0,
           resume: bool = True) -> dict[str, Any]:
    identity = _load_design(outcomes_dir)
    m1_manifest = outcomes_dir / "M1_AUDIT_CAMPAIGN.json"
    m1 = json.loads(m1_manifest.read_text())
    if m1.get("status") != "pass" or m1.get("new_fem_count") != 40:
        raise RuntimeError("M2 requires a passed 40-record M1 campaign")
    reuse = _load_m1_reuse(m1_manifest)
    manifest_path = outcomes_dir / "M2_PRODUCTION_CAMPAIGN.json"
    records = _expected_rows(artifact_root, reuse)
    payload = {
        "schema_version": "task005.m2-production-campaign.v1",
        "campaign_id": CASE_ID_M2, "dataset_id": DATASET_ID,
        "forward_solver_sha": FORWARD_SOLVER_SHA, "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID, "step": {"h": "half", "w": "half"},
        "state_order": list(STATES), "angle_order": [row[0] for row in ANGLE_CANDIDATES],
        "max_production_states": 64, "new_fem_count": sum(1 for r in records.values() if r["new_fem"]),
        "reused_m1_count": sum(1 for r in records.values() if not r["new_fem"]),
        "status": "reserved", "stop_reason": None, "validation_target_accessed": False,
        "records": records,
    }
    if manifest_path.is_file() and resume:
        old = json.loads(manifest_path.read_text())
        if old.get("dataset_id") != DATASET_ID or old.get("forward_solver_sha") != FORWARD_SOLVER_SHA:
            raise RuntimeError("existing M2 manifest identity mismatch")
        payload["records"] = old.get("records", records)
        payload["new_fem_count"] = old.get("new_fem_count", payload["new_fem_count"])
        payload["reused_m1_count"] = old.get("reused_m1_count", payload["reused_m1_count"])
    _write(manifest_path, payload)
    driver = SURROGATE_ROOT / "src/surrogate/doe/forward_driver.py"
    for key, row in payload["records"].items():
        if not row.get("new_fem"):
            continue
        if row.get("status") == "measured_pass" and row.get("sample_path") and Path(row["sample_path"]).is_file() and resume:
            continue
        print(f"M2 start {key}: h={row['height_nm']} w={row['width_nm']} g={row['grazing_deg']} a={row['azimuth_deg']}", flush=True)
        row["attempted"] = True; row["attempt_number"] = int(row.get("attempt_number", 0)) + 1; row["status"] = "running"
        _write(manifest_path, payload)
        command = _command(root=forward_root, driver=driver,
                           row={**row, "design_index": row["design_index"]},
                           baseline_sha=FORWARD_SOLVER_SHA, timeout_seconds=timeout_seconds)
        log_name = key.replace("/", "__").replace("+", "plus").replace("-", "minus") + ".log"
        return_code = _run_with_heartbeat(command, cwd=forward_root,
                                          log_path=artifact_root / "m2_logs" / log_name, label=key,
                                          phase="M2")
        summary_path = Path(row["run_directory"]) / "task005_driver_summary.json"
        summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
        row.update({"return_code": return_code, "status": summary.get("status", "failed_runner"),
                    "sample_path": summary.get("sample_path"), "formal_record_sha256": summary.get("formal_record_sha256"),
                    "execution_sha256": summary.get("execution_sha256"), "watchdog": summary.get("watchdog")})
        _write(manifest_path, payload)
        if return_code != 0 or row["status"] != "measured_pass":
            payload["status"] = "controlled_stop"; payload["stop_reason"] = f"first_unexplained_failure:{key}:{row['status']}"
            _write(manifest_path, payload); return payload
    dataset_dir = artifact_root / "dataset"
    built = build_dataset(outcomes_dir=outcomes_dir, train_dir=train_dir,
                          dataset_dir=dataset_dir, campaign=payload)
    dataset_copy = outcomes_dir / "M2_DATASET_MANIFEST.json"
    _write(dataset_copy, built["manifest"])
    payload["status"] = "pass"; payload["stop_reason"] = None; payload["dataset_dir"] = str(dataset_dir.resolve())
    payload["dataset_manifest_sha256"] = _digest(dataset_dir / "dataset_manifest.json")
    _write(manifest_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", type=Path, default=SURROGATE_ROOT / "surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/outcomes")
    parser.add_argument("--train-dir", type=Path, default=SURROGATE_ROOT / "benchmarks/artifacts/cases/127_task004_active_learning_round1/train112")
    parser.add_argument("--artifact-root", type=Path, default=SURROGATE_ROOT / "benchmarks/artifacts/cases/132_task005_sensitivity_dataset")
    parser.add_argument("--forward-root", type=Path, default=FORWARD_ROOT)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    result = run_m2(outcomes_dir=args.outcomes.resolve(), train_dir=args.train_dir.resolve(),
                    artifact_root=args.artifact_root.resolve(), forward_root=args.forward_root.resolve(),
                    timeout_seconds=args.timeout_seconds, resume=not args.no_resume)
    print(json.dumps({"status": result.get("status"), "stop_reason": result.get("stop_reason"),
                      "new_fem_count": result.get("new_fem_count"), "reused_m1_count": result.get("reused_m1_count")}, indent=2))
    return 0 if result.get("status") == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
