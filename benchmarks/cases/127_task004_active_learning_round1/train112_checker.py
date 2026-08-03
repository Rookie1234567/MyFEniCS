"""Independent identity checker for the immutable Task004 train112 package.

The checker recomputes package file hashes and the 96+16 design identity from
coordinates.  It only reads the response-bearing training package and the
training-only CV report; validation responses are not opened.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
TRAIN112 = REPO / "benchmarks/artifacts/cases/127_task004_active_learning_round1/train112"
TRAIN96_DESIGN = REPO / "benchmarks/cases/123_task004_nominal_geometry_angle_surrogate/training_design.json"
ROUND1_DESIGN = ROOT / "records/round1_training_design.json"
COMBINED_DESIGN = ROOT / "records/train112_design.json"
CV = REPO / "surrogate_tasks/task004_nominal_geometry_angle_surrogate/outcomes/train112_cv/training_cv.json"
OUT = ROOT / "records/case127_train112_check.json"
FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
DATASET_ID = "task004_angle_nominal_p5_ny4_train112_v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def design_rows(path: Path) -> list[list[float]]:
    payload = json.loads(path.read_text())
    return [[float(np.round(float(point[key]), 12)) for key in
             ("height_nm", "width_x_nm", "grazing_deg", "azimuth_deg")]
            for point in payload["points"]]


def main() -> int:
    checks: dict[str, bool] = {}
    errors: list[str] = []
    manifest_path = TRAIN112 / "dataset_manifest.json"
    hashes_path = TRAIN112 / "file_hashes.json"
    required = (manifest_path, hashes_path, TRAIN96_DESIGN, ROUND1_DESIGN,
                COMBINED_DESIGN, CV)
    checks["required_artifacts_present"] = all(path.is_file() for path in required)
    if not checks["required_artifacts_present"]:
        errors.append("train112 identity or training-CV artifact is missing")
    manifest: dict = {}
    if manifest_path.is_file() and hashes_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        expected = json.loads(hashes_path.read_text())
        actual = {path.name: digest(path) for path in sorted(TRAIN112.iterdir())
                  if path.is_file() and path.name != "file_hashes.json"}
        checks["package_hashes_recomputed"] = actual == expected
        arrays_expected = {
            "angles.npy": ([112, 2], "float64"),
            "inputs.npy": ([112, 4], "float64"),
            "aggregates.npy": ([112, 4], "float64"),
            "order_amplitudes.npy": ([112, 22, 2, 2], "float64"),
            "order_powers.npy": ([112, 22, 2], "float64"),
            "power_carrying_mask.npy": ([112, 22, 2], "bool"),
            "sample_ids.npy": ([112], "<U64"),
            "train_indices.npy": ([112], "int64"),
        }
        array_identity = True
        for name, (shape, dtype) in arrays_expected.items():
            path = TRAIN112 / name
            if not path.is_file():
                array_identity = False
                continue
            value = np.load(path, mmap_mode="r", allow_pickle=False)
            array_identity = bool(array_identity and list(value.shape) == shape and
                                  str(value.dtype) == dtype)
        checks["array_identity"] = array_identity
        checks["manifest_identity"] = bool(
            manifest.get("dataset_id") == DATASET_ID and
            manifest.get("sample_count") == 112 and
            manifest.get("training_count") == 112 and
            manifest.get("forward_solver_sha") == FORWARD_SHA and
            manifest.get("source_sha") == FORWARD_SHA and
            manifest.get("source_dirty") is False and
            manifest.get("immutable") is True and
            manifest.get("validation_target_accessed") is False and
            manifest.get("blind_validation_count") == 0
        )
    else:
        checks["package_hashes_recomputed"] = False
        checks["array_identity"] = False
        checks["manifest_identity"] = False

    try:
        expected_rows = design_rows(TRAIN96_DESIGN) + design_rows(ROUND1_DESIGN)
        combined_payload = json.loads(COMBINED_DESIGN.read_text())
        combined_rows = design_rows(COMBINED_DESIGN)
        checks["exact_96_plus_16_design"] = bool(
            len(expected_rows) == 112 and combined_rows == expected_rows and
            combined_payload.get("point_count") == 112 and
            combined_payload.get("point_tuple_sha256") == canonical(expected_rows) and
            manifest.get("training_tuple_sha256") == canonical(expected_rows) and
            np.array_equal(np.load(TRAIN112 / "inputs.npy", allow_pickle=False).round(12),
                           np.asarray(expected_rows, dtype=np.float64))
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        checks["exact_96_plus_16_design"] = False
        errors.append(f"design identity failed: {exc}")

    if CV.is_file():
        cv = json.loads(CV.read_text())
        selected = cv.get("selected_candidate")
        candidates = {row.get("candidate") for row in cv.get("candidate_results", [])}
        checks["training_only_cv_identity"] = bool(
            cv.get("schema_version") == "task004.training-cv.v3" and
            cv.get("dataset_id") == DATASET_ID and
            cv.get("forward_solver_sha") == FORWARD_SHA and
            cv.get("training_count") == 112 and
            cv.get("validation_target_accessed") is False and
            selected in candidates and isinstance(cv.get("training_gate"), bool)
        )
        checks["cv_result_preserves_negative_gate"] = bool(
            cv.get("training_gate") is False and
            cv.get("active_learning_eligibility") is False
        )
    else:
        checks["training_only_cv_identity"] = False
        checks["cv_result_preserves_negative_gate"] = False

    checks["no_model_lock_or_validation"] = bool(
        not (REPO / "surrogate_tasks/task004_nominal_geometry_angle_surrogate/outcomes/train112_cv/ANGLE_MODEL_SELECTION_LOCK.json").exists() and
        manifest.get("validation_target_accessed") is False
    )
    checks["all_checks"] = bool(all(checks.values()) and not errors)
    result = {
        "schema_version": "case127.train112-check.v1",
        "status": "pass" if checks["all_checks"] else "fail",
        "checks": checks,
        "errors": errors,
        "dataset_id": DATASET_ID,
        "training_count": 112,
        "forward_solver_sha": FORWARD_SHA,
        "validation_target_accessed": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
