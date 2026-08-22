"""Recompute the Task040 Level-A Gate from one ignored raw run root."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

HARD_STOP_BYTES = 45 * 2**30
MANDATORY_RHO_LIMIT = 1.0
WORST_RHO_LIMIT = 0.95
PREFERRED_RHO_LIMIT = 0.90
ZERO_MAP_LIMIT = 1e-13
REPEAT_LIMIT = 1e-10
LINEARITY_LIMIT = 1e-10
PREFERRED_LABELS = {
    "modal_traction_positive",
    "modal_traction_negative",
    "external_dtn_coupling",
}
EXPECTED_LABELS = [
    "physical_side_rhs",
    "modal_traction_positive",
    "modal_traction_negative",
    "external_dtn_coupling",
    "fixed_random_repeat_0",
    "fixed_random_repeat_1",
]

__all__ = ["recompute_level_a_gate"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def recompute_level_a_gate(run_root: str | Path) -> dict[str, Any]:
    root = Path(run_root)
    worker_path = root / "worker" / "run_summary.json"
    watchdog_path = root / "watchdog_summary.json"
    samples_path = root / "process_tree_samples.jsonl"
    worker = _read_json(worker_path)
    watchdog = _read_json(watchdog_path)
    reports = worker["action"]["reports"]
    labels = [record["label"] for record in reports]
    mandatory = [record for record in reports if record["label"] != "physical_side_rhs"]
    rho_by_label = {
        record["label"]: record.get("true_residual_relative") for record in reports
    }
    mandatory_rhos = [record["true_residual_relative"] for record in mandatory]
    worst_rho = max(mandatory_rhos)
    physical = next(
        record for record in reports if record["label"] == "physical_side_rhs"
    )
    action_identity = worker["action"]["action_identity"]
    factors = worker["action"]["factor_inventory"]
    masses = worker["interface_masses"]
    samples = [
        json.loads(line)
        for line in samples_path.read_text().splitlines()
        if line.strip()
    ]
    peak_rss = max(
        sample["resource_authority"]["memory_authority_bytes"] for sample in samples
    )
    peak_swap = max(
        sample["resource_authority"]["process_tree"]["swap_bytes"] for sample in samples
    )
    checks = {
        "source_labels": labels == EXPECTED_LABELS and len(labels) == len(set(labels)),
        "finite": all(
            record["finite"]
            and _finite(record["source_norm"])
            and _finite(record["output_norm"])
            and _finite(record["true_residual_norm"])
            for record in mandatory
        )
        and physical["finite"]
        and _finite(physical["output_norm"]),
        "zero_map": physical["source_norm"] <= ZERO_MAP_LIMIT
        and physical["output_norm"] <= ZERO_MAP_LIMIT,
        "repeat": all(record["repeat_error"] <= REPEAT_LIMIT for record in reports),
        "linearity": worker["action"]["gate"]["linearity_relative_error"]
        <= LINEARITY_LIMIT,
        "restriction_prolongation": action_identity["restriction_prolongation_pass"]
        and not action_identity["global_numpy_copy"]
        and not action_identity["subdomain_vectors_global_numpy_copy"],
        "bare_operator_unchanged": action_identity["bare_operator_unchanged"],
        "interface_mass_support": len(masses) == 2
        and all(
            mass["finite"]
            and mass["support_sets_exact_match"]
            and mass["bare_operator_unchanged"]
            for mass in masses
        ),
        "factor_inventory": factors["cross_section_factor_count_ready"] == 3
        and factors["full_side_exact_factor_count"] == 0
        and factors["global_direct_factor_count"] == 0
        and factors["nested_ksp_count"] == 0
        and factors["system_direct_factor_count_observed"] == 0
        and not factors["system_global_A_materialized_observed"]
        and factors["oracle_only"]
        and not factors["scalable_candidate"]
        and worker["cleanup"]["factor_owner"]["after"]["factor_count_after_cleanup"]
        == 0,
        "mandatory_rho": all(rho < MANDATORY_RHO_LIMIT for rho in mandatory_rhos),
        "worst_rho": worst_rho <= WORST_RHO_LIMIT,
        "preferred_rho": all(
            rho_by_label[label] <= PREFERRED_RHO_LIMIT for label in PREFERRED_LABELS
        ),
        "watchdog": watchdog["return_code"] == 0
        and watchdog["termination_reason"] == "natural_exit"
        and watchdog["run_summary_present"]
        and watchdog["all_status_readable"]
        and watchdog["source_sha"] == worker["source_sha"]
        and watchdog["run_summary_sha256"] == _sha256(worker_path),
        "resource": peak_rss < HARD_STOP_BYTES
        and peak_swap == 0
        and watchdog["peak_swap_bytes"] == 0
        and watchdog["peak_dedicated_cgroup_swap_bytes"] == 0,
    }
    raw_paths = {
        "watchdog_summary.json": watchdog_path,
        "worker/run_summary.json": worker_path,
        "process_tree_samples.jsonl": samples_path,
        "memory_stage_markers.raw.jsonl": root / "memory_stage_markers.raw.jsonl",
        "memory_stages.jsonl": root / "memory_stages.jsonl",
    }
    return {
        "schema": "task040.level_a.recomputed_gate.v1",
        "source_sha": worker["source_sha"],
        "raw_hashes": {name: _sha256(path) for name, path in raw_paths.items()},
        "rho_by_label": rho_by_label,
        "worst_mandatory_rho": worst_rho,
        "peak_rss_bytes": peak_rss,
        "peak_rss_gib": peak_rss / 2**30,
        "peak_swap_bytes": peak_swap,
        "wall_seconds": max(sample["elapsed_seconds"] for sample in samples),
        "factor_inventory": {
            "cross_section_ready": factors["cross_section_factor_count_ready"],
            "full_side": factors["full_side_exact_factor_count"],
            "global_direct": factors["global_direct_factor_count"],
            "nested_ksp": factors["nested_ksp_count"],
            "cleanup_after": worker["cleanup"]["factor_owner"]["after"][
                "factor_count_after_cleanup"
            ],
        },
        "checks": checks,
        "gate_pass": all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(recompute_level_a_gate(args.run_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
