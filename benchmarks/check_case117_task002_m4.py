"""Build and verify Task002 Review-V5 M4P/M4 Case117 evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from src.forward_data.provenance import canonical_hash, file_hash
from src.forward_data.task002_dataset import write_compact_dataset
from src.forward_data.task002_dataset_checker import verify_exact_design_dataset
from src.forward_data.task002_m4 import (
    formal_record_to_production_sample, rebind_frozen_designs,
)


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/cases/117_task002_p5_bulk_campaign"
RECORDS = CASE / "records"
ART = ROOT / "benchmarks/artifacts/cases/117/m4"
CASE116 = ROOT / "benchmarks/cases/116_task002_single_fidelity_design"
DESIGNS = ART / "rebound_designs"
CAMPAIGN = ART / "campaign_manifest.json"
DATASET = ART / "compact_dataset"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def p5_leakage_authority() -> dict[str, Any]:
    authority = _read(
        ROOT / "benchmarks/cases/115_task002_full3d_hierarchy_qualification/records/"
        "full3d_p5_angle_map.json"
    )
    maxima = {name: {"value": 0.0, "argmax": None} for name in (
        "reflection_power_sum", "transmission_power_sum", "total_power",
        "absolute_amplitude",
    )}
    rows = []
    for source in authority["rows"]:
        paths = list(Path(source["run"]).rglob("dtn_port_diffraction_orders_3d.json"))
        if len(paths) != 1:
            raise ValueError(f"p5 leakage authority raw path ambiguity: {source['run']}")
        raw_path = paths[0]
        reflection = transmission = maximum_amplitude = 0.0
        amplitude_argmax = None
        for order in _read(raw_path)["orders"]:
            if int(order["n"]) == 0:
                continue
            power = float(order.get("power_ratio") or 0.0)
            if order["side"] == "top":
                reflection += power
            else:
                transmission += power
            amplitude = order.get("outgoing_amplitude_at_boundary")
            magnitude = 0.0 if amplitude is None else math.hypot(*amplitude)
            if magnitude > maximum_amplitude:
                maximum_amplitude = magnitude
                amplitude_argmax = {
                    key: order[key] for key in ("m", "n", "side", "polarization")
                }
        angle = [source["grazing_deg"], source["azimuth_deg"]]
        values = {
            "reflection_power_sum": reflection,
            "transmission_power_sum": transmission,
            "total_power": reflection + transmission,
            "absolute_amplitude": maximum_amplitude,
        }
        for name, value in values.items():
            if value > maxima[name]["value"]:
                maxima[name] = {
                    "value": value, "argmax": {"angle": angle,
                    "order": amplitude_argmax if name == "absolute_amplitude" else None},
                }
        rows.append({"angle": angle, **values, "raw": str(raw_path),
                     "raw_sha256": file_hash(raw_path)})
    return {
        "schema_version": "task002.case117-p5-leakage-authority.v1",
        "authority_point_count": len(rows), "maxima": maxima, "rows": rows,
        "frozen_gates": {"total_power_max": 1e-7, "absolute_amplitude_max": 1e-4},
        "gates": {
            "p5_80_angle_authority": len(rows) == 80,
            "total_power_supports_gate": maxima["total_power"]["value"] <= 1e-7,
            "amplitude_supports_gate": maxima["absolute_amplitude"]["value"] <= 1e-4,
        },
    }


def _directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def compact_equivalence() -> dict[str, Any]:
    rows = []
    for name in ("center_g0p5_a45", "width17p5_g10_a45"):
        ordinary = ART / "ab" / name / "ordinary"
        compact = ART / "ab" / name / "compact"
        left = _read(ordinary / "results/task002_full3d_record.json")
        right = _read(compact / "results/task002_full3d_record.json")
        aggregate_delta = {
            key: abs(float(left["observables"][key]) - float(right["observables"][key]))
            for key in ("R_total", "T_total", "A_balance", "A_volume",
                        "true_relative_residual", "energy_closure_error")
        }
        left_mother = left["observables"]["mother_response"]
        right_mother = right["observables"]["mother_response"]
        raw_left = _read(ordinary / "results/dtn_port_diffraction_orders_3d.json")
        raw_right = _read(compact / "results/dtn_port_diffraction_orders_3d.json")
        forbidden = [str(path) for pattern in ("*.vtu", "*.pvd", "*.bp")
                     for path in compact.rglob(pattern)]
        rows.append({
            "point": name, "aggregate_abs_delta": aggregate_delta,
            "raw_orders_exact": raw_left == raw_right,
            "mother_response_exact": left_mother == right_mother,
            "ordinary_payload_bytes": _directory_bytes(ordinary),
            "compact_payload_bytes": _directory_bytes(compact),
            "compact_forbidden_field_files": forbidden,
            "pass": max(aggregate_delta.values()) <= 1e-12
                    and raw_left == raw_right and left_mother == right_mother
                    and not forbidden and right["gates"]["compact_output_identity"],
        })
    return {
        "schema_version": "task002.case117-compact-output-equivalence.v1",
        "rows": rows, "gates": {"two_points": len(rows) == 2,
                                  "all_equivalent": all(row["pass"] for row in rows)},
    }


def campaign_samples() -> list[dict[str, Any]]:
    manifest = _read(CAMPAIGN)
    samples = []
    for row in sorted(manifest["samples"].values(),
                      key=lambda value: (value["split"] != "train", value["design_index"])):
        if row["status"] != "measured_pass":
            continue
        run = Path(row["run_directory"])
        samples.append(formal_record_to_production_sample(
            manifest_row=row,
            formal_record_path=run / "results/task002_full3d_record.json",
            execution_path=run / "execution.json",
        ))
    return samples


def campaign_record(baseline_sha: str) -> dict[str, Any]:
    manifest = _read(CAMPAIGN)
    rows = list(manifest["samples"].values())
    train = [row for row in rows if row["split"] == "train"]
    validation = [row for row in rows if row["split"] == "frozen_validation"]
    canary = [row for row in train if row["design_index"] in range(64, 80)]
    passed = lambda values: sum(row["status"] == "measured_pass" for row in values)
    return {
        "schema_version": "task002.case117-campaign-completion.v1",
        "baseline_sha": baseline_sha, "manifest_sha256": file_hash(CAMPAIGN),
        "canary_pass_count": passed(canary), "training_pass_count": passed(train),
        "frozen_validation_pass_count": passed(validation),
        "status_inventory": {
            status: sum(row["status"] == status for row in rows)
            for status in sorted({row["status"] for row in rows})
        },
        "gates": {"canary_16": passed(canary) == 16,
                  "training_96": passed(train) == 96,
                  "validation_16": passed(validation) == 16,
                  "no_failure": all(row["status"] == "measured_pass" for row in rows),
                  "one_source": {row["source_sha"] for row in rows} == {baseline_sha}},
    }


def build_dataset(baseline_sha: str) -> dict[str, Any]:
    samples = campaign_samples()
    result = write_compact_dataset(samples, output_dir=DATASET,
                                   dataset_id="task002_m4_p5_112_v2")
    exact = verify_exact_design_dataset(
        DATASET, training_design_path=DESIGNS / "training_design.json",
        validation_design_path=DESIGNS / "frozen_validation_design.json",
        baseline_sha=baseline_sha,
    )
    return {"writer": result, "exact_checker": exact}


def write_preflight(baseline_sha: str) -> None:
    RECORDS.mkdir(parents=True, exist_ok=True)
    _write(RECORDS / "p5_leakage_authority.json", p5_leakage_authority())
    _write(RECORDS / "compact_output_equivalence.json", compact_equivalence())
    rebind = rebind_frozen_designs(
        source_dir=CASE116, output_dir=DESIGNS, baseline_sha=baseline_sha,
    )
    _write(RECORDS / "design_rebind.json", rebind)
    _write(RECORDS / "campaign_preflight.json", {
        "schema_version": "task002.case117-campaign-preflight.v1",
        "baseline_sha": baseline_sha, "campaign_schema": "task002.s-p5-design-campaign.v3",
        "output_profile": "compact_surrogate_record",
        "gates": {"leakage_authority": all(p5_leakage_authority()["gates"].values()),
                  "compact_ab": all(compact_equivalence()["gates"].values()),
                  "design_rebind": rebind["pass"]},
    })


def write_final(baseline_sha: str) -> None:
    campaign = campaign_record(baseline_sha)
    verification = verify_exact_design_dataset(
        DATASET, training_design_path=DESIGNS / "training_design.json",
        validation_design_path=DESIGNS / "frozen_validation_design.json",
        baseline_sha=baseline_sha,
    )
    _write(RECORDS / "canary_16.json", {"pass_count": campaign["canary_pass_count"],
                                        "gate": campaign["canary_pass_count"] == 16})
    _write(RECORDS / "training_96.json", {"pass_count": campaign["training_pass_count"],
                                          "gate": campaign["training_pass_count"] == 96})
    _write(RECORDS / "frozen_validation_16.json", {
        "pass_count": campaign["frozen_validation_pass_count"],
        "gate": campaign["frozen_validation_pass_count"] == 16,
    })
    _write(RECORDS / "dataset_verification.json", verification)
    samples = campaign_samples()
    _write(RECORDS / "resource_summary.json", {
        "sample_count": len(samples), "all_resource_gates": all(
            all(sample["resource_gates"].values()) for sample in samples),
        "campaign": campaign,
    })


def verify_final() -> int:
    required = (
        "campaign_preflight.json", "p5_leakage_authority.json",
        "compact_output_equivalence.json", "design_rebind.json", "canary_16.json",
        "training_96.json", "frozen_validation_16.json", "dataset_verification.json",
        "resource_summary.json",
    )
    missing = [name for name in required if not (RECORDS / name).is_file()]
    if missing:
        print(json.dumps({"missing": missing}, indent=2)); return 2
    values = {name: _read(RECORDS / name) for name in required}
    gates = {
        "preflight": all(values["campaign_preflight.json"]["gates"].values()),
        "leakage": all(values["p5_leakage_authority.json"]["gates"].values()),
        "compact_ab": all(values["compact_output_equivalence.json"]["gates"].values()),
        "rebind": values["design_rebind.json"]["pass"],
        "canary": values["canary_16.json"]["gate"],
        "training": values["training_96.json"]["gate"],
        "validation": values["frozen_validation_16.json"]["gate"],
        "dataset": values["dataset_verification.json"]["status"] == "pass",
        "resources": values["resource_summary.json"]["all_resource_gates"],
    }
    print(json.dumps(gates, indent=2)); return 0 if all(gates.values()) else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-sha")
    parser.add_argument("--write-preflight", action="store_true")
    parser.add_argument("--build-dataset", action="store_true")
    parser.add_argument("--write-final", action="store_true")
    parser.add_argument("--verify-final", action="store_true")
    args = parser.parse_args()
    if args.verify_final:
        return verify_final()
    if not args.baseline_sha or len(args.baseline_sha) != 40:
        parser.error("--baseline-sha is required and must be full length")
    if args.write_preflight:
        write_preflight(args.baseline_sha)
    if args.build_dataset:
        result = build_dataset(args.baseline_sha); print(json.dumps(result, indent=2))
    if args.write_final:
        write_final(args.baseline_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
