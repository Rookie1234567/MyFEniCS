"""Build and score the 112+16 Task003 Round-2 compact dataset.

The builder starts from the already sealed 104+16 Round-1 package and appends
exactly the eight measured Round-2 records.  The sixteen validation rows are
copied only as opaque array rows/metadata for dataset identity; training CV
loads only the explicit training indices.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from src.forward_data.task002_m4 import formal_record_to_production_sample
from .cv import run_training_cv
from .dataset import sha256_file


BASE_DATASET = Path(
    "benchmarks/artifacts/cases/121_task003_active_learning_round1_retry_cachefix/compact_dataset"
)
ROUND2_ARTIFACT = Path("benchmarks/artifacts/cases/122_task003_round2")
CASE = Path("benchmarks/cases/122_task003_round1_fixed_reference_and_optional_round2")
EVIDENCE = Path("benchmarks/cases/122_task003_round2")
DATASET = ROUND2_ARTIFACT / "compact_dataset"
MANIFEST = ROUND2_ARTIFACT / "campaign_manifest.json"
OUT = Path("surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/outcomes")


def _canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def _arrays_from_records(records: list[dict[str, Any]]) -> tuple[np.ndarray, ...]:
    inputs = np.asarray([row["inputs"] for row in records], dtype=np.float64)
    aggregates = np.asarray(
        [[row["aggregates"][name] for name in
          ("R_total", "T_total", "A_balance", "A_volume")] for row in records],
        dtype=np.float64,
    )
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


def _round2_samples() -> list[dict[str, Any]]:
    manifest = json.loads(MANIFEST.read_text())
    paths = []
    for index in range(8):
        key = f"task003_active_learning_round2_training:{index:04d}"
        row = manifest["samples"].get(key)
        if row is None or row.get("status") != "measured_pass":
            raise RuntimeError(f"Round2 manifest row is not measured_pass: {key}")
        run_directory = Path(row["run_directory"])
        record_path = run_directory / "results" / "task002_full3d_record.json"
        execution_path = run_directory / "execution.json"
        if not record_path.is_file() or not execution_path.is_file():
            raise RuntimeError(f"missing formal record/execution for {key}")
        paths.append((row, record_path, execution_path))
    return [formal_record_to_production_sample(
        manifest_row=row, formal_record_path=record_path,
        execution_path=execution_path,
    ) for row, record_path, execution_path in paths]


def build_dataset() -> dict[str, Any]:
    DATASET.mkdir(parents=True, exist_ok=True)
    base_records = [json.loads(line) for line in
                    (BASE_DATASET / "sample_records.jsonl").read_text().splitlines()
                    if line.strip()]
    if len(base_records) != 120:
        raise RuntimeError(f"expected 120 rows in Round1 package, found {len(base_records)}")
    appended = _round2_samples()
    if len(appended) != 8:
        raise RuntimeError("Round2 must append exactly eight samples")
    records = base_records + appended
    if len({row["sample_id"] for row in records}) != 128:
        raise RuntimeError("sample IDs are not unique after Round2 append")

    old_arrays = {name: np.load(BASE_DATASET / name, allow_pickle=False)
                  for name in ("inputs.npy", "aggregates.npy", "order_amplitudes.npy",
                               "order_powers.npy", "power_carrying_mask.npy")}
    add_arrays = _arrays_from_records(appended)
    arrays = {
        "inputs.npy": np.vstack((old_arrays["inputs.npy"], add_arrays[0])),
        "aggregates.npy": np.vstack((old_arrays["aggregates.npy"], add_arrays[1])),
        "order_amplitudes.npy": np.concatenate((old_arrays["order_amplitudes.npy"], add_arrays[2])),
        "order_powers.npy": np.concatenate((old_arrays["order_powers.npy"], add_arrays[3])),
        "power_carrying_mask.npy": np.concatenate((old_arrays["power_carrying_mask.npy"], add_arrays[4])),
    }
    for name, array in arrays.items():
        np.save(DATASET / name, array, allow_pickle=False)
    train_indices = np.asarray(list(range(96)) + list(range(112, 128)), dtype=np.int64)
    validation_indices = np.arange(96, 112, dtype=np.int64)
    np.save(DATASET / "train_indices.npy", train_indices)
    np.save(DATASET / "frozen_validation_indices.npy", validation_indices)
    (DATASET / "order_identity.json").write_bytes((BASE_DATASET / "order_identity.json").read_bytes())
    (DATASET / "sample_records.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                for row in records)
    )

    array_meta = {name: {"shape": list(array.shape), "dtype": str(array.dtype)}
                  for name, array in arrays.items()}
    manifest_out = {
        "schema_version": "task003.s-p5-ny4-round2-dataset.v1",
        "dataset_id": "task003_m3t_round2_p5_ny4_112_v1",
        "dataset_source_sha": "10e3356ba8364286a452077f71d7e3b92ea24cd5",
        "parameter_schema_version": "task002.s-p5-ny4-production-parameters.v3",
        "observable_schema_version": "task002.fixed-n0-orders.v3",
        "production_model_id": "S_PROD_FULL3D_STATIC_P5_H10_NY4",
        "production_solver_route_id": "full3d_static_uniform_n1curl_p5_h10_ny4",
        "production_axis_cell_counts": [6, 4, 14],
        "sample_count": 128, "training_count": 112, "frozen_validation_count": 16,
        "arrays": {**array_meta,
                   "train_indices.npy": {"shape": [112], "dtype": "int64"},
                   "frozen_validation_indices.npy": {"shape": [16], "dtype": "int64"}},
        "sample_ids_hash": _canonical([row["sample_id"] for row in records]),
        "train_tuple_sha256": _canonical([row["inputs"] for row in records if row["split"] == "train"]),
        "frozen_validation_tuple_sha256": _canonical(
            [row["inputs"] for row in records if row["split"] == "frozen_validation"]),
        "round1_tuple_sha256": _canonical([row["inputs"] for row in records[112:120]]),
        "round2_tuple_sha256": _canonical([row["inputs"] for row in records[120:128]]),
        "validation_target_accessed": False,
    }
    (DATASET / "dataset_manifest.json").write_text(json.dumps(manifest_out, indent=2) + "\n")
    hashes = {path.name: sha256_file(path) for path in DATASET.iterdir()
              if path.is_file() and path.name != "file_hashes.json"}
    (DATASET / "file_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")

    records_dir = CASE / "records"
    evidence_dir = EVIDENCE / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for index, row in enumerate(appended):
        payload = json.dumps(row, indent=2) + "\n"
        (records_dir / f"{index:04d}_{row['sample_id'][:12]}.json").write_text(payload)
        (evidence_dir / f"{index:04d}_{row['sample_id'][:12]}.json").write_text(payload)
    return manifest_out


def run_cv() -> dict[str, Any]:
    report = run_training_cv(DATASET)
    oof = report.pop("oof_records", [])
    report["dataset_id"] = "task003_m3t_round2_p5_ny4_112_v1"
    report["training_count"] = 112
    (OUT / "training_cv_112.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    (OUT / "training_cv_112_oof.json").write_text(json.dumps({
        "schema_version": "task003.training-oof.v3", "dataset_id": report["dataset_id"],
        "training_count": 112, "selected_candidate": report["selected_candidate"],
        "records": oof,
    }, indent=2, allow_nan=False) + "\n")
    return report


def main() -> int:
    manifest = build_dataset()
    report = run_cv()
    print(json.dumps({"dataset_id": manifest["dataset_id"], "training_count": 112,
                      "frozen_validation_count": 16,
                      "status": report["status"], "selected_candidate": report["selected_candidate"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
