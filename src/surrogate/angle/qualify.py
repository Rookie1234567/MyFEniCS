"""Clean-SHA anchor qualification for Task004."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .dataset import _records_from_manifest


def _order_identity(order: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(order.get("side")), str(order.get("port_side")),
        int(order.get("m")), int(order.get("n")),
        tuple(str(name) for name in order.get("components", {}).keys()),
    )


def _max_shared_difference(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    aggregates = max(abs(float(old["aggregates"][name]) - float(new["aggregates"][name]))
                     for name in ("R_total", "T_total", "A_balance", "A_volume"))
    powers = 0.0; amplitudes = 0.0
    identity_mismatch = []
    wavevector_mismatch = 0
    mask_mismatch = 0
    dispersion_mismatch = 0
    old_orders = old["mother_response"]["orders"]
    new_orders = new["mother_response"]["orders"]
    if len(old_orders) != len(new_orders):
        identity_mismatch.append("order_count")
    for index, (old_order, new_order) in enumerate(zip(old_orders, new_orders)):
        if _order_identity(old_order) != _order_identity(new_order):
            identity_mismatch.append(f"order_identity[{index}]")
        if bool(old_order.get("dispersion_propagating")) != bool(
            new_order.get("dispersion_propagating")
        ):
            dispersion_mismatch += 1
        if bool(old_order.get("power_carrying")) != bool(new_order.get("power_carrying")):
            mask_mismatch += 1
        for vector_name in ("kx", "ky", "kz"):
            old_vector = old_order.get(vector_name) or {}
            new_vector = new_order.get(vector_name) or {}
            for part in ("re", "im"):
                if abs(float(old_vector.get(part, 0.0)) - float(new_vector.get(part, 0.0))) > 1.0e-12:
                    wavevector_mismatch += 1
        for component in ("s", "p"):
            old_value = old_order["components"][component]
            new_value = new_order["components"][component]
            if bool(old_value.get("power_carrying")) != bool(new_value.get("power_carrying")):
                mask_mismatch += 1
            if (old_value.get("power") is None) != (new_value.get("power") is None):
                mask_mismatch += 1
            for part in ("amplitude_re", "amplitude_im"):
                if (old_value.get(part) is None) != (new_value.get(part) is None):
                    mask_mismatch += 1
            if old_value.get("power") is not None and new_value.get("power") is not None:
                powers = max(powers, abs(float(old_value["power"]) - float(new_value["power"])))
            for part in ("amplitude_re", "amplitude_im"):
                if old_value.get(part) is not None and new_value.get(part) is not None:
                    amplitudes = max(amplitudes, abs(float(old_value[part]) - float(new_value[part])))
    return {"aggregate_max_abs": aggregates, "shared_order_power_max_abs": powers,
            "shared_complex_amplitude_max_abs": amplitudes,
            "order_identity_mismatches": identity_mismatch,
            "wavevector_mismatch_count": wavevector_mismatch,
            "mask_mismatch_count": mask_mismatch,
            "dispersion_mismatch_count": dispersion_mismatch}


def qualify(*, repo_root: Path, campaign_manifest: Path, output: Path,
            source_sha: str,
            anchor_design_id: str = "task004_anchor_training_v1") -> dict[str, Any]:
    old_rows = [json.loads(line) for line in
                (repo_root / "benchmarks/artifacts/cases/119/m4e/compact_dataset/sample_records.jsonl").read_text().splitlines()
                if line.strip() and json.loads(line).get("split") == "train"]
    reference = {tuple(float(v) for v in row["inputs"]): row for row in old_rows}
    new_rows = _records_from_manifest(campaign_manifest, anchor_design_id, 5)
    results = []
    for row in new_rows:
        key = tuple(float(v) for v in row["inputs"])
        old = reference.get(key)
        if old is None:
            raise RuntimeError(f"Case119 anchor missing: {key}")
        diff = _max_shared_difference(old, row)
        identity = {
            "model_id": row["model_id"], "solver_route_id": row["solver_route_id"],
            "axis_cell_counts": row["axis_cell_counts"],
            "source_sha": row["source_sha"], "source_dirty": row["source_dirty"],
            "observable_schema_version": row.get("observable_schema_version"),
            "parameter_schema_version": row.get("parameter_schema_version"),
            "mumps_icntl_14": row.get("solver_identity", {}).get(
                "requested_mat_mumps_icntl_14"
            ),
        }
        passed = (diff["aggregate_max_abs"] <= 1.0e-10
                  and diff["shared_order_power_max_abs"] <= 1.0e-10
                  and diff["shared_complex_amplitude_max_abs"] <= 1.0e-9
                  and identity["model_id"] == "S_PROD_FULL3D_STATIC_P5_H10_NY4"
                  and identity["solver_route_id"] == "full3d_static_uniform_n1curl_p5_h10_ny4"
                  and identity["axis_cell_counts"] == [6, 4, 14]
                  and identity["source_sha"] == source_sha and identity["source_dirty"] is False)
        passed = passed and not diff["order_identity_mismatches"]
        passed = passed and diff["wavevector_mismatch_count"] == 0
        passed = passed and diff["mask_mismatch_count"] == 0
        passed = passed and diff["dispersion_mismatch_count"] == 0
        passed = passed and identity["observable_schema_version"] == "task002.fixed-n0-orders.v3"
        passed = passed and identity["parameter_schema_version"] == "task002.s-p5-ny4-production-parameters.v3"
        passed = passed and identity["mumps_icntl_14"] in {40, 80, 120}
        results.append({"inputs": list(key), "differences": diff, "identity": identity,
                        "pass": passed})
    report = {"schema_version": "task004.forward-baseline.v2", "source_sha": source_sha,
              "anchor_count": len(results), "anchors": results,
              "gate": {"aggregate_le_1e-10": True, "power_le_1e-10": True,
                        "amplitude_le_1e-9": True, "identity_match": True},
              "status": "pass" if all(row["pass"] for row in results) else "controlled_stop"}
    report["gate"] = {
        "aggregate_le_1e-10": all(r["differences"]["aggregate_max_abs"] <= 1.0e-10 for r in results),
        "power_le_1e-10": all(r["differences"]["shared_order_power_max_abs"] <= 1.0e-10 for r in results),
        "amplitude_le_1e-9": all(r["differences"]["shared_complex_amplitude_max_abs"] <= 1.0e-9 for r in results),
        "identity_match": all(r["pass"] for r in results),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report
