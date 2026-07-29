"""Independent lightweight checker for Task002 Case112 contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.forward_data.provenance import canonical_hash
from src.forward_data.task002_dataset import verify_compact_dataset
from src.forward_data.task002_design import (
    audit_order_window, fixed_hf_angle_pilot, lf_angle_pilot,
)


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks" / "cases" / "112_s_continuous_illumination_multifidelity_surrogate"


def build_scaffold_record() -> dict[str, Any]:
    lf = lf_angle_pilot()
    hf = fixed_hf_angle_pilot()
    audit = audit_order_window()
    return {
        "schema_version": "task002.case112-scaffold-record.v1",
        "lf_angle_pilot_count": len(lf),
        "fixed_hf_angle_pilot_count": len(hf),
        "lf_angle_design_hash": canonical_hash(lf),
        "fixed_hf_angle_design_hash": canonical_hash(hf),
        "order_window_audit": audit,
        "gates": {
            "lf_count_49": len(lf) == 49,
            "hf_count_9": len(hf) == 9,
            "order_window_complete": bool(audit["coverage_pass"]),
        },
    }


def check_scaffold(*, check_records: bool) -> dict[str, Any]:
    config = json.loads((CASE / "config.json").read_text())
    expected = json.loads((CASE / "expected.json").read_text())
    if config["polarization"] != "S" or config["wavelength_nm"] != 13.5:
        raise ValueError("Case112 fixed physics mismatch")
    if expected["bulk_generation_allowed_before_m2_gate"]:
        raise ValueError("Case112 must fail closed before the M2 gate")
    record = build_scaffold_record()
    if not all(record["gates"].values()):
        raise ValueError(f"Case112 scaffold gate failed: {record['gates']}")
    if check_records:
        tracked = json.loads((CASE / "records" / "m1_scaffold.json").read_text())
        if tracked != record:
            raise ValueError("Case112 tracked M1 scaffold record is stale")
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-records", action="store_true")
    parser.add_argument("--dataset", type=Path)
    args = parser.parse_args()
    result = check_scaffold(check_records=args.check_records)
    if args.dataset is not None:
        result["dataset"] = verify_compact_dataset(args.dataset)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
