"""Build and score the 104+16 Task003 Round-1 compact dataset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from src.forward_data.task002_m4 import formal_record_to_production_sample
from .cv import run_training_cv
from .dataset import CASE119_ROOT, sha256_file


CASE = Path("benchmarks/artifacts/cases/121_task003_active_learning_round1_retry_cachefix")
CASE_EVIDENCE = Path("benchmarks/cases/121_task003_active_learning_round1")
NEW_DATASET = CASE / "compact_dataset"
MANIFEST = CASE / "campaign_manifest.json"
DESIGN = Path("benchmarks/cases/121_task003_active_learning_round1/round1_design.json")
OUT = Path("surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/outcomes")


def _canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def _new_arrays(records: list[dict[str, Any]]) -> tuple[np.ndarray, ...]:
    inputs = np.asarray([row["inputs"] for row in records], dtype=np.float64)
    aggregates = np.asarray([[row["aggregates"][name] for name in
                              ("R_total", "T_total", "A_balance", "A_volume")]
                             for row in records], dtype=np.float64)
    amplitudes = np.full((len(records), 22, 2, 2), np.nan, dtype=np.float64)
    powers = np.full((len(records), 22, 2), np.nan, dtype=np.float64)
    mask = np.zeros((len(records), 22, 2), dtype=bool)
    for ri, row in enumerate(records):
        for oi, order in enumerate(row["mother_response"]["orders"]):
            for ci, component in enumerate(("s", "p")):
                value = order["components"][component]
                if not value.get("power_carrying", False):
                    continue
                mask[ri, oi, ci] = True
                amplitudes[ri, oi, ci, 0] = float(value["amplitude_re"])
                amplitudes[ri, oi, ci, 1] = float(value["amplitude_im"])
                powers[ri, oi, ci] = float(value["power"])
    return inputs, aggregates, amplitudes, powers, mask


def build_dataset() -> dict[str, Any]:
    NEW_DATASET.mkdir(parents=True, exist_ok=True)
    old = CASE119_ROOT
    old_arrays = {name: np.load(old / name, allow_pickle=False) for name in
                  ("inputs.npy", "aggregates.npy", "order_amplitudes.npy",
                   "order_powers.npy", "power_carrying_mask.npy")}
    old_records = [json.loads(line) for line in (old / "sample_records.jsonl").read_text().splitlines() if line]
    manifest = json.loads(MANIFEST.read_text())
    appended: list[dict[str, Any]] = []
    record_paths = sorted((CASE / "task003_active_learning_round1_training").glob(
        "*/attempt_*/results/task002_full3d_record.json"))
    if len(record_paths) != 8:
        raise RuntimeError(f"expected exactly 8 formal records, found {len(record_paths)}")
    for index, record_path in enumerate(record_paths):
        key = f"task003_active_learning_round1_training:{index:04d}"
        row = manifest["samples"][key]
        execution_path = record_path.parent.parent / "execution.json"
        appended.append(formal_record_to_production_sample(
            manifest_row=row, formal_record_path=record_path,
            execution_path=execution_path,
        ))
    new_inputs, new_aggregates, new_amplitudes, new_powers, new_mask = _new_arrays(appended)
    arrays = {
        "inputs.npy": np.vstack((old_arrays["inputs.npy"], new_inputs)),
        "aggregates.npy": np.vstack((old_arrays["aggregates.npy"], new_aggregates)),
        "order_amplitudes.npy": np.concatenate((old_arrays["order_amplitudes.npy"], new_amplitudes)),
        "order_powers.npy": np.concatenate((old_arrays["order_powers.npy"], new_powers)),
        "power_carrying_mask.npy": np.concatenate((old_arrays["power_carrying_mask.npy"], new_mask)),
    }
    for name, array in arrays.items():
        np.save(NEW_DATASET / name, array, allow_pickle=False)
    np.save(NEW_DATASET / "train_indices.npy", np.asarray(list(range(96)) + list(range(112, 120)), dtype=np.int64))
    np.save(NEW_DATASET / "frozen_validation_indices.npy", np.arange(96, 112, dtype=np.int64))
    for name in ("order_identity.json",):
        (NEW_DATASET / name).write_bytes((old / name).read_bytes())
    records = old_records + appended
    (NEW_DATASET / "sample_records.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in records)
    )
    array_meta = {name: {"shape": list(array.shape), "dtype": str(array.dtype)}
                  for name, array in arrays.items()}
    manifest_out = {
        "schema_version": "task003.s-p5-ny4-round1-dataset.v1",
        "dataset_id": "task003_m3s_round1_p5_ny4_104_v1",
        "dataset_source_sha": "10e3356ba8364286a452077f71d7e3b92ea24cd5",
        "parameter_schema_version": "task002.s-p5-ny4-production-parameters.v3",
        "observable_schema_version": "task002.fixed-n0-orders.v3",
        "production_model_id": "S_PROD_FULL3D_STATIC_P5_H10_NY4",
        "production_solver_route_id": "full3d_static_uniform_n1curl_p5_h10_ny4",
        "production_axis_cell_counts": [6, 4, 14],
        "sample_count": 120, "training_count": 104, "frozen_validation_count": 16,
        "arrays": {**array_meta,
                   "train_indices.npy": {"shape": [104], "dtype": "int64"},
                   "frozen_validation_indices.npy": {"shape": [16], "dtype": "int64"}},
        "sample_ids_hash": _canonical([row["sample_id"] for row in records]),
        "train_tuple_sha256": _canonical([row["inputs"] for row in records if row["split"] == "train"]),
        "frozen_validation_tuple_sha256": _canonical([row["inputs"] for row in records if row["split"] == "frozen_validation"]),
        "validation_target_accessed": False,
    }
    (NEW_DATASET / "dataset_manifest.json").write_text(json.dumps(manifest_out, indent=2) + "\n")
    hashes = {path.name: sha256_file(path) for path in NEW_DATASET.iterdir() if path.is_file()}
    (NEW_DATASET / "file_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")
    for index, row in enumerate(appended):
        for records_dir in (CASE / "records", CASE_EVIDENCE / "records"):
            records_dir.mkdir(parents=True, exist_ok=True)
            (records_dir / f"{index:04d}_{row['sample_id'][:12]}.json").write_text(
                json.dumps(row, indent=2) + "\n")
    return manifest_out


def run_cv() -> dict[str, Any]:
    report = run_training_cv(NEW_DATASET)
    oof = report.pop("oof_records", [])
    report["dataset_id"] = "task003_m3s_round1_p5_ny4_104_v1"
    report["training_count"] = 104
    (OUT / "training_cv_104.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    (OUT / "training_cv_104_oof.json").write_text(json.dumps({
        "schema_version": "task003.training-oof.v3", "dataset_id": report["dataset_id"],
        "training_count": 104, "selected_candidate": report["selected_candidate"],
        "records": oof,
    }, indent=2, allow_nan=False) + "\n")
    return report


def main() -> int:
    manifest = build_dataset()
    report = run_cv()
    print(json.dumps({"dataset_id": manifest["dataset_id"], "training_count": 104,
                      "frozen_validation_count": 16,
                      "status": report["status"], "selected_candidate": report["selected_candidate"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
