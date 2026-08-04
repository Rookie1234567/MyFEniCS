"""Independent Task006 M0 design/reuse checker.

The checker duplicates the tuple construction and only opens the explicitly
listed Task004/Task005 training records.  It never searches the artifact tree
and never opens any blind-geometry response.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
OBSERVABLE = "task002.fixed-n0-orders.v3"
DATASET_ID = "task006_fixed_A05_A07_A09_hw_train37_p5_ny4_v1"
ANGLES = (("A05", 2.0, 0.0), ("A07", 2.0, 90.0), ("A09", 4.0, 60.0))
H = (115.0, 117.5, 118.75, 120.0, 121.25, 122.5, 125.0)
W = (16.0, 16.5, 16.75, 17.0, 17.25, 17.5, 18.0)
BLIND = (
    (117.5, 16.5), (117.5, 16.75), (117.5, 17.25), (117.5, 17.5),
    (118.75, 16.5), (118.75, 17.5), (121.25, 16.5), (121.25, 17.5),
    (122.5, 16.5), (122.5, 16.75), (122.5, 17.25), (122.5, 17.5),
)
CENTER = ((120.0, 17.0), (118.75, 17.0), (121.25, 17.0), (120.0, 16.75),
          (120.0, 17.25), (118.75, 16.75), (118.75, 17.25), (121.25, 17.25))
COARSE = ((117.5, 17.0), (122.5, 17.0), (120.0, 16.5), (120.0, 17.5))
MISSING = ((121.25, 16.75),)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _mother() -> list[list[float]]:
    return [[h, w] for h in H for w in W]


def _train() -> list[list[float]]:
    boundary = [[h, w] for h in H for w in W if h in (115.0, 125.0) or w in (16.0, 18.0)]
    extras = [list(x) for x in CENTER + COARSE + MISSING]
    result: list[list[float]] = []
    for row in boundary + extras:
        if row not in result:
            result.append(row)
    return result


def _sample_from_source(path: Path, line_match: list[float] | None) -> dict[str, Any]:
    if line_match is not None:
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        matches = [row for row in rows if row.get("inputs") == line_match]
        if len(matches) != 1:
            raise ValueError(f"expected one exact JSONL reuse row, found {len(matches)}: {line_match}")
        return matches[0]
    return json.loads(path.read_text())


def _check_sample(row: dict[str, Any], *, h: float, w: float, grazing: float, azimuth: float) -> bool:
    inputs = row.get("inputs")
    return bool(
        inputs == [h, w, grazing, azimuth]
        and row.get("status") == "measured_pass"
        and row.get("source_sha") == FORWARD_SHA
        and row.get("source_dirty") is False
        and row.get("model_id") == MODEL_ID
        and row.get("solver_route_id") == ROUTE_ID
        and row.get("observable_schema_version") == OBSERVABLE
        and row.get("config_identity", {}).get("mpi_ranks") == 2
        and row.get("config_identity", {}).get("threads_per_rank") == 1
        and row.get("config_identity", {}).get("linear_solver", {}).get("mat_mumps_icntl_14") == 40
    )


def check(root: Path) -> tuple[dict[str, bool], list[str]]:
    outcomes = root / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes"
    errors: list[str] = []
    checks: dict[str, bool] = {}
    try:
        fixed = json.loads((outcomes / "FIXED_ILLUMINATION_CONTRACT.json").read_text())
        mother = json.loads((outcomes / "HW_MOTHER_GRID.json").read_text())
        train = json.loads((outcomes / "HW_TRAIN37_DESIGN.json").read_text())
        blind = json.loads((outcomes / "HW_BLIND12_DESIGN.json").read_text())
        reuse = json.loads((outcomes / "HW_REUSE_INVENTORY.json").read_text())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"required_outputs": False}, [f"read failed: {exc}"]

    expected_mother = _mother()
    expected_train = _train()
    expected_blind = [list(x) for x in BLIND]
    checks["required_outputs"] = True
    checks["frozen_identity"] = bool(
        mother.get("status") == "frozen" and mother.get("created_without_fem") is True
        and mother.get("dataset_id") == DATASET_ID and mother.get("forward_solver_sha") == FORWARD_SHA
        and mother.get("model_id") == MODEL_ID and mother.get("solver_route_id") == ROUTE_ID
        and mother.get("observable_schema_version") == OBSERVABLE
        and mother.get("new_fem_count") == 0 and mother.get("blind_response_accessed") is False
    )
    checks["exact_mother_grid"] = bool(
        mother.get("mother_count") == 49 and mother.get("mother_geometries") == expected_mother
        and mother.get("mother_tuple_sha256") == canonical(expected_mother)
    )
    checks["exact_train37"] = bool(
        train.get("geometry_count") == 37 and train.get("geometries") == expected_train
        and train.get("tuple_sha256") == canonical(expected_train)
        and train.get("expected_new_fem_count") == 79
        and train.get("blind_response_accessed") is False
    )
    checks["exact_blind12_frozen"] = bool(
        blind.get("status") == "frozen_not_run" and blind.get("count") == 12
        and blind.get("geometries") == expected_blind
        and blind.get("tuple_sha256") == canonical(expected_blind)
        and blind.get("fem_run") is False and blind.get("responses_accessed") is False
        and blind.get("all_strictly_interior") is True
    )
    checks["partition_49_37_12"] = bool(
        len(set(map(tuple, expected_train)).intersection(set(BLIND))) == 0
        and len(expected_train) + len(BLIND) == 49
        and set(map(tuple, expected_train + expected_blind)) == set(map(tuple, expected_mother))
    )
    checks["fixed_angles_and_channels"] = bool(
        fixed.get("status") == "frozen" and fixed.get("forward_solver_sha") == FORWARD_SHA
        and [row.get("angle_id") for row in fixed.get("angles", [])] == [x[0] for x in ANGLES]
        and [row.get("grazing_deg") for row in fixed.get("angles", [])] == [x[1] for x in ANGLES]
        and [row.get("azimuth_deg") for row in fixed.get("angles", [])] == [x[2] for x in ANGLES]
        and all(row.get("channel_identity") == [["reflection", 0, 0], ["transmission", 0, 0]] for row in fixed.get("angles", []))
        and fixed.get("blind_response_accessed") is False
    )
    lock_rel = fixed.get("task005_v2_lock", {}).get("path")
    checks["task005_lock_bound"] = bool(
        lock_rel and (root / lock_rel).is_file()
        and fixed.get("task005_v2_lock", {}).get("sha256") == digest(root / lock_rel)
    )
    rows = reuse.get("records", [])
    checks["reuse_count_and_budget"] = bool(
        reuse.get("reuse_count") == 32 and reuse.get("new_record_count") == 79
        and reuse.get("new_fem_count") == 79 and len(rows) == 111
        and reuse.get("blind_response_accessed") is False
    )
    reuse_pass = True
    seen_keys: set[str] = set()
    for item in rows:
        key = item.get("key")
        if key in seen_keys:
            reuse_pass = False
            errors.append(f"duplicate reuse key: {key}")
        seen_keys.add(key)
        path = Path(item.get("source_path", "")) if item.get("source_path") else None
        if not item.get("reuse"):
            continue
        if path is None or not path.is_file():
            reuse_pass = False
            errors.append(f"missing explicit reuse path: {path}")
            continue
        try:
            row = _sample_from_source(path, item.get("line_match"))
            ok = _check_sample(row, h=float(item["height_nm"]), w=float(item["width_nm"]),
                               grazing=float(item["grazing_deg"]), azimuth=float(item["azimuth_deg"]))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            ok = False
            errors.append(f"reuse read failed {key}: {exc}")
        if not ok:
            reuse_pass = False
            errors.append(f"reuse identity mismatch: {key}")
    checks["explicit_reuse_records_exact"] = reuse_pass and len(seen_keys) == 111
    checks["no_blind_access_claim"] = bool(
        all(not bool(value) for value in (mother.get("blind_response_accessed"), train.get("blind_response_accessed"), blind.get("responses_accessed"), reuse.get("blind_response_accessed"), fixed.get("blind_response_accessed")))
    )
    if not all(checks.values()):
        errors.extend(f"failed:{name}" for name, value in checks.items() if not value)
    return checks, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "records/case135_check.json")
    args = parser.parse_args()
    checks, errors = check(args.root.resolve())
    result = {
        "schema_version": "task006.case135-m0-check.v1",
        "status": "pass" if all(checks.values()) else "failed",
        "checks": checks, "errors": errors,
        "new_fem_count": 0, "blind_response_accessed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
