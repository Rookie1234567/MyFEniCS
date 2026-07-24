"""Write the Task035b unscaled-evanescent-port controlled-stop record."""

from __future__ import annotations

import argparse
from argparse import Namespace
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Sequence

from benchmarks.run_task035_actual_r5 import (
    _fixed_trace_resource_preflight,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = (
    "codex/20260723-task35b-high-order-local-hp-resource-envelope"
)
DEFAULT_OUTPUT = Path(
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
    "records/fixed_trace_h15_evanescent_buffer1_preflight_"
    "controlled_stop.json"
)
SOURCE_FILES = (
    "benchmarks/run_task035_actual_r5.py",
    "src/common/config_3d.py",
    "src/common/modes_3d.py",
    "src/solvers/dtn_port_3d.py",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _clean_source_gate(
    repo_root: Path,
    verified_clean_sha: str,
) -> dict[str, Any]:
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    checks = {
        "head_matches_verified_sha": head == verified_clean_sha,
        "expected_branch": branch == EXPECTED_BRANCH,
        "tracked_and_untracked_worktree_clean": status == "",
    }
    if not all(checks.values()):
        raise SystemExit(
            "controlled-stop source gate failed: "
            + ", ".join(
                name for name, passed in checks.items() if not passed
            )
        )
    return {
        "commit_sha": head,
        "branch": branch,
        "tracked_source_dirty": False,
        "stable_and_clean_before": True,
        "checks": checks,
    }


def build_controlled_stop_record(
    repo_root: Path,
    *,
    source: dict[str, Any],
) -> dict[str, Any]:
    """Build compact evidence without launching MPI or a PDE."""

    args = Namespace(
        h_nm=15.0,
        fixed_interior_degree=6,
        fixed_trace_dtn_quadrature_degree=None,
        fixed_trace_dtn_evanescent_buffer=1,
        mpi_size=8,
        fixed_trace_directional_recovery=False,
    )
    preflight = _fixed_trace_resource_preflight(args)
    scaling = dict(preflight["port_basis_scaling_preflight"])
    mode_rows = list(scaling.pop("mode_rows"))
    worst_phase = min(
        mode_rows,
        key=lambda row: row["abs_boundary_phase"],
    )
    worst_denominator = min(
        mode_rows,
        key=lambda row: row["projection_denominator"],
    )
    side_summaries = {
        side: {
            "mode_count": len(selected),
            "minimum_abs_boundary_phase": min(
                row["abs_boundary_phase"] for row in selected
            ),
            "minimum_projection_denominator": min(
                row["projection_denominator"] for row in selected
            ),
            "maximum_projection_denominator": max(
                row["projection_denominator"] for row in selected
            ),
        }
        for side in ("top", "bottom")
        for selected in [
            [row for row in mode_rows if row["side"] == side]
        ]
    }
    qualification_checks = {
        "preflight_stopped_before_pde": preflight["pass"] is False,
        "only_failed_check_is_unscaled_basis_safety": (
            [
                name
                for name, passed in preflight["checks"].items()
                if not passed
            ]
            == ["unscaled_port_basis_numerically_safe"]
        ),
        "buffer1_mode_count_is_340": (
            preflight["predicted_resources"]["dtn_auxiliary_rows"]
            == 340
        ),
        "buffer1_evanescent_count_is_260": (
            preflight["predicted_resources"]["dtn_evanescent_rows"]
            == 260
        ),
        "buffer1_ordered_identity_frozen": (
            preflight["predicted_resources"][
                "dtn_mode_identity_sha256"
            ]
            == "74f785341325c2f88a6512747bb4cf0d2cad1d8b8dc66fd0c7e2a63ee758f629"
        ),
        "pde_not_authorized": scaling["pde_authorized"] is False,
        "ordinary_default_unchanged": (
            scaling["ordinary_default_changed"] is False
        ),
    }
    passed = all(qualification_checks.values())
    return {
        "schema_version": (
            "task035b.fixed-trace-port-preflight-controlled-stop.v1"
        ),
        "benchmark_id": (
            "task035b_fixed_trace_h15_evanescent_buffer1_preflight"
        ),
        "status": (
            "controlled_stop_unscaled_evanescent_port_basis"
            if passed
            else "preflight_evidence_invalid"
        ),
        "pass": passed,
        "classification": "controlled_negative_safety_evidence",
        "pde": {
            "status": "not_run",
            "mpi_size_planned": 8,
            "heavy_case_started": False,
            "solver_failure": False,
        },
        "scope": {
            "geometry": "Task034 fixed rectangular block grating",
            "h_nm": 15.0,
            "trace_degree": 5,
            "interior_degree": 6,
            "dtn_order_policy": "auto_propagating",
            "dtn_evanescent_buffer": 1,
            "effective_surface_quadrature_degree": 25,
            "ordinary_default_changed": False,
            "scientific_gate_relaxed": False,
        },
        "source": source,
        "source_file_sha256": {
            path: _sha256(repo_root / path) for path in SOURCE_FILES
        },
        "qualification": {
            "pass": passed,
            "checks": qualification_checks,
        },
        "resource_projection": preflight["predicted_resources"],
        "port_basis_scaling_preflight": {
            **scaling,
            "worst_boundary_phase_mode": worst_phase,
            "worst_projection_denominator_mode": worst_denominator,
            "by_side": side_summaries,
        },
        "decision": {
            "buffer1_pde_authorized": False,
            "reason": (
                "The current global-z evanescent basis produces an "
                "augmented row/column scale ratio far beyond machine "
                "precision. A MUMPS failure would not classify physical "
                "buffer convergence."
            ),
            "reopen_condition": (
                "Normalize evanescent modes at each port plane (or prove an "
                "equivalent equilibration), freeze the 80 propagating "
                "channel convention, and pass operator-equivalence tests."
            ),
            "next_safe_port_case": "h15 fixed trace with DtN quadrature q31",
        },
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = args.repo_root.resolve()
    source = _clean_source_gate(
        repo_root,
        args.verified_clean_sha,
    )
    output = (
        args.output
        if args.output.is_absolute()
        else repo_root / args.output
    ).resolve()
    if not output.is_relative_to(repo_root):
        raise SystemExit("controlled-stop output must remain in the repo")
    output.parent.mkdir(parents=True, exist_ok=True)
    record = build_controlled_stop_record(
        repo_root,
        source=source,
    )
    with output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return 0 if record["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
