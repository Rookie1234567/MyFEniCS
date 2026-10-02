"""Read-only checks of frozen trace Galerkin evidence; no FE or solver imports."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


def equation_pass(a):
    fields = ("schur_relative", "native_relative", "augmented_relative",
              "original_total_augmented_relative", "port_full_rhs_relative",
              "port_operation_relative")
    return bool(all(np.isfinite(a[k]) and a[k] <= 1e-6 for k in fields)
                and np.isfinite(a["recovery_relative"]) and a["recovery_relative"] <= 1e-10
                and np.isfinite(a["schur_original_identity_operation_relative"])
                and a["schur_original_identity_operation_relative"] <= 1e-10
                and a["slave_storage_max"] == 0)


def physical_pass(row, reference_pass):
    a, f, c = row["audit"], row["fields"], row["comparison"]
    return bool(reference_pass and equation_pass(a)
                and np.isfinite(a["independent_DOLFINx_total_native_relative"])
                and a["independent_DOLFINx_total_native_relative"] <= 1e-6
                and all(np.isfinite(v) and v <= 1e-4 for v in f.values())
                and np.isfinite(c["ordered_complex_ports_relative"])
                and c["ordered_complex_ports_relative"] <= 1e-4
                and all(np.isfinite(v) and v <= 1e-5 for v in c["power_absolute_differences"].values())
                and np.isfinite(c["max_channel_power_difference"])
                and c["max_channel_power_difference"] <= 1e-6
                and np.isfinite(c["energy_closure_absolute"])
                and c["energy_closure_absolute"] <= 1e-5)


def check(records, *, suffix="v22"):
    records = Path(records)
    def read(name):
        return json.loads((records / (name + "_" + suffix + ".json")).read_text())
    fields, gates = read("field_checks"), read("qualification_and_dispatch")
    inventory = read("source_inventory")
    errors, states = [], {}
    for key, entry in inventory["raw_results"].items():
        if hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
            errors.append("raw result hash differs: " + key)
    ref = fields["reference_audit"]
    reference_pass = equation_pass(ref) and ref["independent_DOLFINx_total_native_relative"] <= 1e-6
    if reference_pass != fields["reference_native_pass"]:
        errors.append("reference qualification differs from raw residual")
    verify = json.loads(Path(inventory["raw_results"]["VERIFY"]["path"]).read_text())
    if verify["reference_feedback_to_solver"] or not verify["queue_frozen"]:
        errors.append("frozen reference boundary differs")
    channels = list(csv.DictReader((records / ("field_channels_" + suffix + ".csv")).open()))
    candidates = {r["state"]: r for r in csv.DictReader((records / ("candidate_comparison_" + suffix + ".csv")).open())}
    for name, row in fields["rows"].items():
        original = verify["rows"][name]
        if any(row[k] != original[k] for k in ("audit", "fields", "comparison", "power", "volume_absorption")):
            errors.append("compact metrics differ from frozen raw: " + name)
        passed = physical_pass(row, reference_pass)
        states[name] = dict(original_equation=equation_pass(row["audit"]), complete_same_discrete=passed)
        if states[name] != gates["states"][name] or passed != (candidates[name]["strict_qualified"] == "True"):
            errors.append("declared qualification differs from raw metrics: " + name)
        own = [r for r in channels if r["state"] == name]
        if sorted(int(r["index"]) for r in own) != list(range(40)):
            errors.append("full 40-channel inventory differs: " + name)
    if sum(r["complete_same_discrete"] for r in states.values()) != gates["strict_pass_count"]:
        errors.append("pass total differs")
    if any(gates["counts"][k] > v for k, v in gates["limits"].items()):
        errors.append("campaign cost cap exceeded")
    return dict(status="EVIDENCE_CONSISTENT" if not errors else "EVIDENCE_INVALID",
                errors=errors, states=states, solver_actions=0, reference_feedback=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("records", type=Path)
    p.add_argument("--suffix", default="v22")
    a = p.parse_args()
    result = check(a.records, suffix=a.suffix)
    print(json.dumps(result))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
