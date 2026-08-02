"""Case123 design and controlled-stop checker.

This checker is intentionally response-blind: with no qualified anchor it
verifies design identities and the preserved failure evidence, but never
opens Task003 validation arrays or fabricates a Task004 pass.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
OUT = REPO / "surrogate_tasks/task004_nominal_geometry_angle_surrogate/outcomes"
BASELINE = "7fe366304023c32bf2e8ddcacdb2ada9996d3e7c"


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def tuples(design):
    return [[float(np.round(float(row[key]), 12)) for key in ("height_nm", "width_x_nm", "grazing_deg", "azimuth_deg")]
            for row in design["points"]]


def main() -> int:
    names = {"training": "training_design.json", "validation": "frozen_validation_design.json",
             "candidate": "candidate_pool.json", "anchors": "anchor_design.json"}
    designs = {key: json.loads((ROOT / filename).read_text()) for key, filename in names.items()}
    baseline = json.loads((OUT / "TASK004_FORWARD_BASELINE.json").read_text())
    checks = {
        "single_source_sha": all(item.get("source_sha") == BASELINE and item.get("source_dirty") is False
                                  for item in designs.values()),
        "production_identity": all(item.get("production_model_id") == "S_PROD_FULL3D_STATIC_P5_H10_NY4"
                                    and item.get("production_solver_route_id") == "full3d_static_uniform_n1curl_p5_h10_ny4"
                                    and item.get("observable_schema_version") == "task002.fixed-n0-orders.v3"
                                    for item in designs.values()),
        "nominal_geometry": all(all(abs(float(row["height_nm"]) - 120.0) < 1e-12
                                    and abs(float(row["width_x_nm"]) - 17.0) < 1e-12
                                    for row in item["points"]) for item in designs.values()),
        "counts_96_24_4096_5": (designs["training"]["point_count"] == 96
                                 and designs["validation"]["point_count"] == 24
                                 and designs["candidate"]["point_count"] == 4096
                                 and designs["anchors"]["point_count"] == 5),
        "design_hashes_rebuild": all(canonical(tuples(item)) == item["point_tuple_sha256"]
                                      for item in designs.values()),
        "training_validation_disjoint": not (set(map(tuple, tuples(designs["training"])))
                                              & set(map(tuple, tuples(designs["validation"])) )),
        "baseline_controlled_stop": baseline.get("status") == "controlled_stop"
            and baseline.get("source_sha") == BASELINE,
        "first_failure_direct_lu": baseline.get("failure", {}).get("status") == "failed_direct_lu_exception"
            and baseline.get("failure", {}).get("formal_record_present") is False,
        "no_task003_access": baseline.get("task003_round3_started") is False
            and baseline.get("task003_frozen_validation_accessed") is False,
    }
    result = {"status": "controlled_stop" if all(checks.values()) else "fail",
              "checks": checks, "training_responses": "not_run",
              "blind_validation_responses": "sealed_not_run",
              "task003_frozen_validation_accessed": False}
    (ROOT / "expected.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "controlled_stop" else 1


if __name__ == "__main__":
    raise SystemExit(main())
