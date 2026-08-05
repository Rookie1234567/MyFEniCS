"""Refresh M4A audits whose hidden-MAP post-hoc stop used the corrected best-point rule."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUTCOMES = ROOT / "surrogate_tasks/task007_schneider_objective_gp_benchmark/outcomes"
sys.path.insert(0, str(ROOT / "src"))
spec = importlib.util.spec_from_file_location("case148_run", Path(__file__).with_name("run.py"))
case148 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(case148)

from surrogate.task007.continuous import Legendre3ResponseOracle  # noqa: E402
from surrogate.task007.m4a import initialization_cost_study  # noqa: E402


def main() -> int:
    oracle = Legendre3ResponseOracle(ROOT)
    m3_targets = case148._m3_targets(OUTCOMES)
    m3_maps = case148._m3_maps(OUTCOMES)
    acquisition_payload, acquisition_md = case148.acquisition_report(oracle, OUTCOMES, m3_maps, m3_targets)
    (OUTCOMES / "M4_ACQUISITION_REPLAY_AUDIT.json").write_text(
        json.dumps(acquisition_payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    (OUTCOMES / "M4_ACQUISITION_REPLAY_AUDIT.md").write_text(acquisition_md)
    map_payload = json.loads((OUTCOMES / "M4_MAP_STABILITY_AUDIT.json").read_text())
    cost_payload = initialization_cost_study(oracle, OUTCOMES, map_payload["rows"])
    cost_payload["implementation_source_sha"] = case148.PLACEHOLDER_SHA
    (OUTCOMES / "M4_INITIALIZATION_COST_STUDY.json").write_text(
        json.dumps(cost_payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    cost_lines = [
        "# M4A initialization cost study", "",
        "只比较 I0 existing train37、I1 Sobol12、I2 Sobol37、I3 train37+Sobol6、I4 train37+Sobol12；online query 仍使用冻结连续 EI，初始 response count 与 online count 分开。", "",
        "| init | contract | noise | initial | new FEM vs train37 | median online | p90 | single total median | 10-measurement amortized | 100-measurement amortized | MAP hit fraction |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in cost_payload["rows"]:
        if not row.get("summary"):
            continue
        values = (row["initialization"], row["contract"], row["noise_scenario"], row["initial_count"], row["new_fem_runs_relative_train37"], row["median_online_queries"], row["p90_online_queries"], row["single_measurement_median_total_evaluations"], row["amortized_total_evaluations_10"], row["amortized_total_evaluations_100"], row["map_hit_fraction"])
        cost_lines.append("| " + " | ".join(str(value) for value in values) + " |")
    (OUTCOMES / "M4_INITIALIZATION_COST_STUDY.md").write_text("\n".join(cost_lines) + "\n")
    print(json.dumps({"status": "pass", "acquisition_gate": acquisition_payload["all_gate_pass"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
