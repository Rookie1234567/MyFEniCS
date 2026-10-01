"""Recompute P2 local RHS closure gates from a saved component record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np
from basix.ufl import element

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rhs_norm(seed: int, full_dimension: int, interior_dimension: int) -> float:
    rng = np.random.default_rng(seed)
    # Match _local_checks draw order exactly: action vector, then internal RHS.
    rng.normal(size=full_dimension)
    rng.normal(size=full_dimension)
    rhs = rng.normal(size=interior_dimension) + 1j * rng.normal(
        size=interior_dimension
    )
    return float(np.linalg.norm(rhs))


def _git_facts() -> dict[str, str]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return {
        "head_sha": head,
        "tracked_worktree_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "rechecker_sha256": _sha256(Path(__file__).resolve()),
    }


def _local_gate(checks: dict[str, Any], closures: dict[str, float]) -> bool:
    return bool(
        checks["matrix_frobenius_relative"] <= 1.0e-10
        and checks["action_relative"] <= 1.0e-11
        and checks["schur_relative"] <= 1.0e-8
        and checks["recovery_map_relative"] <= 1.0e-8
        and checks["nonzero_rhs_recovery_solution_relative"] <= 1.0e-8
        and closures["native"] <= 1.0e-10
        and closures["candidate"] <= 1.0e-10
    )


def review(artifact_path: Path, output_path: Path, expected_sha256: str) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite offline P2 review: {output_path}")
    artifact_path = artifact_path.resolve()
    artifact_sha = _sha256(artifact_path)
    if artifact_sha != expected_sha256:
        raise ValueError(
            f"P2 artifact SHA mismatch: expected {expected_sha256}, got {artifact_sha}"
        )
    raw = json.loads(artifact_path.read_text())
    if raw.get("status") != "NOT_QUALIFIED":
        raise ValueError("the saved component is not the reviewed closure-bug artifact")

    basix_element = element("N1curl", "hexahedron", 6).basix_element
    full_dimension = int(basix_element.dim)
    interior_dimension = len(basix_element.entity_dofs[3][0])
    trace_dimension = full_dimension - interior_dimension
    if (full_dimension, interior_dimension, trace_dimension) != (882, 450, 432):
        raise ValueError("the current p6 Basix element differs from the frozen fixture")

    local_rechecks: list[dict[str, Any]] = []
    reviewed_rounds: dict[int, bool] = {1: True, 2: True, 3: True}
    seed_bases = {
        "blocked_vs_reference_metric": 95000,
        "ffcx_vs_blocked": 96000,
        "ffcx_vs_reference_metric": 97000,
    }
    for class_index, row in enumerate(raw["classes_completed"], start=1):
        for round_row in row["rounds"]:
            round_index = int(round_row["round"])
            round_pass = (
                round_row["raw_matrix_action"]["matrix_frobenius_relative"] <= 1.0e-10
                and round_row["raw_matrix_action"]["action_relative"] <= 1.0e-11
                and round_row["oriented_matrix_action"]["matrix_frobenius_relative"] <= 1.0e-10
                and round_row["oriented_matrix_action"]["action_relative"] <= 1.0e-11
            )
            sample = round_row.get("ffcx_sample")
            if sample is not None:
                for role, checks in sample["oriented_local_checks"].items():
                    seed = seed_bases[role] + class_index
                    rhs_norm = _rhs_norm(seed, full_dimension, interior_dimension)
                    closures = {
                        "native": float(
                            checks["native_nonzero_rhs_recovery_closure_absolute"]
                            / rhs_norm
                        ),
                        "candidate": float(
                            checks["candidate_nonzero_rhs_recovery_closure_absolute"]
                            / rhs_norm
                        ),
                    }
                    local_pass = _local_gate(checks, closures)
                    round_pass = round_pass and local_pass
                    local_rechecks.append(
                        {
                            "round": round_index,
                            "class_index": class_index,
                            "material_tag": row["material_tag"],
                            "cell_widths": row["cell_widths"],
                            "comparison": role,
                            "random_seed": seed,
                            "full_dimension": full_dimension,
                            "interior_dimension": interior_dimension,
                            "trace_dimension": trace_dimension,
                            "internal_rhs_norm_recomputed": rhs_norm,
                            "native_residual_absolute_saved": checks[
                                "native_nonzero_rhs_recovery_closure_absolute"
                            ],
                            "candidate_residual_absolute_saved": checks[
                                "candidate_nonzero_rhs_recovery_closure_absolute"
                            ],
                            "native_closure_recomputed": closures["native"],
                            "candidate_closure_recomputed": closures["candidate"],
                            "native_rhs_closure_limit": 1.0e-10,
                            "candidate_rhs_closure_limit": 1.0e-10,
                            "local_gate_passed": local_pass,
                        }
                    )
                if not _local_gate(
                    sample["oriented_local_checks"]["ffcx_vs_blocked"],
                    {
                        "native": local_rechecks[-2]["native_closure_recomputed"],
                        "candidate": local_rechecks[-2]["candidate_closure_recomputed"],
                    },
                ):
                    round_pass = False
                if not _local_gate(
                    sample["oriented_local_checks"]["ffcx_vs_reference_metric"],
                    {
                        "native": local_rechecks[-1]["native_closure_recomputed"],
                        "candidate": local_rechecks[-1]["candidate_closure_recomputed"],
                    },
                ):
                    round_pass = False
                if not _local_gate(
                    sample["oriented_local_checks"]["blocked_vs_reference_metric"],
                    {
                        "native": local_rechecks[-3]["native_closure_recomputed"],
                        "candidate": local_rechecks[-3]["candidate_closure_recomputed"],
                    },
                ):
                    round_pass = False
                for name in ("ffcx_vs_blocked_raw", "ffcx_vs_reference_metric_raw"):
                    facts = sample[name]
                    round_pass = round_pass and bool(
                        facts["matrix_frobenius_relative"] <= 1.0e-10
                        and facts["action_relative"] <= 1.0e-11
                    )
            reviewed_rounds[round_index] = reviewed_rounds[round_index] and round_pass

    ratios = [
        float(item["candidate_over_blocked_ratio"])
        for item in raw["paired_rounds"]
    ]
    numerics_pass = bool(local_rechecks and all(reviewed_rounds.values()))
    repeatable_gain = bool(ratios and all(ratio < 1.0 for ratio in ratios))
    result = {
        "schema": "task40extra.p2.saved-closure-reaudit.v1",
        "status": "COMPONENT_QUALIFIED_FOR_G1_M0_WATCHDOG_TRIAL"
        if numerics_pass and repeatable_gain
        else "NOT_QUALIFIED",
        "scope": "G0 component artifact only; no G1 qualification or production adoption",
        "source_artifact_path": str(artifact_path),
        "source_artifact_sha256": artifact_sha,
        "source_artifact_status_preserved": raw["status"],
        "source_campaign_head": raw["source"]["head_sha"],
        "source_candidate_sha256": raw["source"][
            "task40_reference_metric_solver_sha256"
        ],
        "rechecker_source": _git_facts(),
        "numpy_version": np.__version__,
        "seed_protocol": {
            "baseline_vs_candidate": 95000,
            "ffcx_vs_baseline": 96000,
            "ffcx_vs_candidate": 97000,
            "class_index_base": 1,
            "draw_order": "full complex action vector, complex interior RHS, complex trace",
        },
        "residual_definition": "norm(Aii*x_i + Ait*g_t - b_i) / norm(b_i)",
        "round_gates_recomputed": {str(key): value for key, value in reviewed_rounds.items()},
        "matrix_relative_limit": 1.0e-10,
        "action_relative_limit": 1.0e-11,
        "local_rhs_closure_limit": 1.0e-10,
        "repeatable_candidate_over_blocked_ratios_reused": ratios,
        "numerics_gate_passed": numerics_pass,
        "repeatable_gain_vs_blocked_gram": repeatable_gain,
        "memory_gate_status": "pending G1 M0 user-service/independent-watchdog run",
        "adopt_candidate": False,
        "eligible_for_g1_m0_watchdog_trial": bool(numerics_pass and repeatable_gain),
        "measured_orientation_scope": "one real cell-permutation value per each of 33 raw classes; the 67 oriented-class count is inventoried, not exhaustively transformed",
        "local_rhs_rechecks": local_rechecks,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    result = review(args.artifact, args.output, args.expected_sha256)
    print(
        f"P2_REAUDIT status={result['status']} "
        f"checks={len(result['local_rhs_rechecks'])} "
        f"output={args.output}",
        flush=True,
    )


if __name__ == "__main__":
    main()
