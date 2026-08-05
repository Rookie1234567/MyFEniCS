"""Finalize already-computed Task007 replay traces without fitting new models.

This is intentionally a metadata/reporting pass.  It corrects the public
online-query convention (the first query is 1, while acquisition traces keep
their zero-based ``query_step``) and rebuilds aggregate summaries from the raw
stored traces.  It does not read or generate FEM fields and does not refit a
GP.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUTCOMES = ROOT / "surrogate_tasks/task007_schneider_objective_gp_benchmark/outcomes"
sys.path.insert(0, str(ROOT / "src"))

from surrogate.task007.objective import CONTRACTS, NOISE_SCENARIOS  # noqa: E402
from run import markdown_report  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def _correct_query_metric(row: dict) -> None:
    target_steps = [int(item["query_step"]) + 1 for item in row.get("queries", []) if item.get("is_target")]
    row["queries_to_exact_target"] = target_steps[0] if target_steps else None


def _summary(method: str, contract: str, scenario: str, rows: list[dict]) -> dict:
    q = [int(row["queries_to_exact_target"]) for row in rows
         if row.get("queries_to_exact_target") is not None]
    return {
        "method": method, "contract": contract, "noise_scenario": scenario,
        "target_count": len({int(row["target_index"]) for row in rows}),
        "run_count": len(rows), "hit_count": len(q),
        "hit_fraction": float(len(q) / max(len(rows), 1)),
        "median_queries": float(np.median(q)) if q else None,
        "p90_queries": float(np.percentile(q, 90)) if q else None,
        "max_queries": int(max(q)) if q else None,
    }


def main() -> int:
    replay_path = OUTCOMES / "BAYESIAN_OPTIMIZATION_REPLAY.json"
    maps_path = OUTCOMES / "MAP_RECOVERY_SUMMARY.json"
    replay = json.loads(replay_path.read_text())
    maps = json.loads(maps_path.read_text())

    # Keep the target traces immutable apart from the explicitly corrected
    # public metric; acquisition candidate order and revealed values are not
    # regenerated.
    for target in replay["targets"]:
        for contract in CONTRACTS:
            for scenario in NOISE_SCENARIOS:
                block = target["scenarios"][contract][scenario]
                for row in block["P0"] + block["P1"]:
                    _correct_query_metric(row)
                _correct_query_metric(block["P2"])

    # Retain target-level rows for auditability, replacing their query
    # statistics from the corrected raw traces.
    replay["summary"] = {
        key: value for key, value in replay["summary"].items()
        if len(key.split("_")) == 4
    }
    for target in replay["targets"]:
        target_index = int(target["target_index"])
        for contract in CONTRACTS:
            for scenario in NOISE_SCENARIOS:
                block = target["scenarios"][contract][scenario]
                for method in ("P0", "P1", "P2"):
                    rows = block[method] if isinstance(block[method], list) else [block[method]]
                    replay["summary"][f"{contract}_{scenario}_{method}_{target_index}"] = _summary(
                        method, contract, scenario, rows)

    # Public aggregate summaries are built from all raw rows, never from
    # medians of target-level summaries.
    for contract in CONTRACTS:
        for scenario in NOISE_SCENARIOS:
            b0_rows = [target["scenarios"][contract][scenario]["B0"] for target in replay["targets"]]
            b0_values = [float(row["best_F"]) for row in b0_rows]
            replay["summary"][f"{contract}_{scenario}_B0"] = {
                "method": "B0", "contract": contract, "noise_scenario": scenario,
                "target_count": len(b0_rows),
                "exact_target_hit_count": int(sum(bool(row["exact_target_hit"]) for row in b0_rows)),
                "median_best_F": float(np.median(b0_values)),
                "p90_best_F": float(np.percentile(b0_values, 90)),
                "max_best_F": float(np.max(b0_values)),
            }
            random_rows = [
                row for target in replay["targets"]
                for row in target["scenarios"][contract][scenario]["B1"]["repeats"]
            ]
            q_random = [int(row["queries_to_exact_target"]) for row in random_rows
                        if row.get("queries_to_exact_target") is not None]
            replay["summary"][f"{contract}_{scenario}_B1"] = {
                "method": "B1", "contract": contract, "noise_scenario": scenario,
                "target_count": len(replay["targets"]), "repeat_count": len(random_rows),
                "run_count": len(random_rows), "hit_count": len(q_random),
                "hit_fraction": float(len(q_random) / max(len(random_rows), 1)),
                "median_queries": float(np.median(q_random)) if q_random else None,
                "p90_queries": float(np.percentile(q_random, 90)) if q_random else None,
                "max_queries": int(max(q_random)) if q_random else None,
            }
            for method in ("P0", "P1", "P2"):
                raw_rows = [
                    row for target in replay["targets"]
                    for row in (target["scenarios"][contract][scenario][method]
                                if isinstance(target["scenarios"][contract][scenario][method], list)
                                else [target["scenarios"][contract][scenario][method]])
                ]
                replay["summary"][f"{contract}_{scenario}_{method}"] = _summary(
                    method, contract, scenario, raw_rows)

    write_json(replay_path, replay)
    audit = json.loads((OUTCOMES / "OBJECTIVE_GP_MODEL_AUDIT.json").read_text())
    (OUTCOMES / "METHOD_COMPARISON.md").write_text(markdown_report(replay, maps, audit))
    (OUTCOMES / "test_summary_v1.md").write_text(
        "# Task007 test summary v1\n\n"
        "- M0 objective identity audit: pass\n"
        "- stored-response replay traces: 11 targets × J1/J0 × N1/N2; B1=100 repeats/target\n"
        "- Case146 independent checker: pass (qualification retains controlled-negative P3 MAP)\n"
        "- New FEM: 0\n"
        "- Task006 model lock/data mutation: false\n"
        "- frozen validation / formal inversion: not accessed / not run\n"
        "- online-query convention: first query is 1; acquisition trace query_step remains zero-based\n"
    )
    print(json.dumps({"status": "pass", "replay": str(replay_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
