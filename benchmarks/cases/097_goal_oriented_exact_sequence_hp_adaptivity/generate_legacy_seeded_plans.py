#!/usr/bin/env python3
"""Generate hash-bound Task035d legacy-seeded h10 variable-p plans.

This is a lightweight mesh/numbering authority, not a Maxwell PDE runner.
The Task035b multi-goal indicators are accepted only as an experimental seed;
every candidate still requires a fresh direct solve and all Task035d gates.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

import dolfinx
import numpy as np
from mpi4py import MPI
from petsc4py import PETSc


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adaptivity.legacy_seeded_variable_p import (  # noqa: E402
    build_legacy_seeded_variable_p_plan,
    load_legacy_multigoal_cell_seed,
)
from src.adaptivity.variable_p_degree_plan import (  # noqa: E402
    variable_p_cell_degree_plan_payload,
)
from src.common.config_3d import target_stage4_config  # noqa: E402
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d  # noqa: E402


CASE = (
    ROOT
    / "benchmarks"
    / "cases"
    / "097_goal_oriented_exact_sequence_hp_adaptivity"
)
RECORDS = CASE / "records"
SEED = RECORDS / "legacy_multigoal_seed_v1.json"
SOURCE_PATHS = (
    "src/adaptivity/legacy_seeded_variable_p.py",
    "src/adaptivity/variable_p_degree_plan.py",
    "src/adaptivity/variable_p_periodic_orbits.py",
    "src/test/test_191_task035d_legacy_seeded_selector.py",
    (
        "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
        "generate_legacy_seeded_plans.py"
    ),
    (
        "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
        "records/legacy_multigoal_seed_v1.json"
    ),
)
TARGETS = {
    "t30": {
        "score_mass": 0.30,
        "counts": {"p4": 144, "p5": 56, "p6": 52},
        "active_fe_dofs": 87_600,
        "independent_trace_rows": 28_910,
        "solve_rows": 28_990,
        "plan_sha256": (
            "862a0347792c356858b405d27f9874cfb9a28b3d75034d73f75c594c5c43c26d"
        ),
    },
    "t25": {
        "score_mass": 0.25,
        "counts": {"p4": 159, "p5": 51, "p6": 42},
        "active_fe_dofs": 82_052,
        "independent_trace_rows": 27_789,
        "solve_rows": 27_869,
        "plan_sha256": (
            "666a20fa5ed4354e380b8286c3b6321b8e6b243e5b89df56ec35a0a869d0f9ad"
        ),
    },
    "t15": {
        "score_mass": 0.15,
        "counts": {"p4": 178, "p5": 46, "p6": 28},
        "active_fe_dofs": 74_522,
        "independent_trace_rows": 25_972,
        "solve_rows": 26_052,
        "plan_sha256": (
            "a940c09f208c03fcbb4c07cd8527313ace3a5c63945eb68e8fe66bfc9860b669"
        ),
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            _json_safe(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _source_identity() -> dict[str, Any]:
    return {
        "commit_sha": _git_head(),
        "file_sha256": {
            path: _sha256(ROOT / path) for path in SOURCE_PATHS
        },
        "ordinary_default_changed": False,
    }


def _environment() -> dict[str, Any]:
    return {
        "dolfinx_version": str(dolfinx.__version__),
        "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
        "petsc_int_type": np.dtype(PETSc.IntType).name,
        "mpi_size": int(MPI.COMM_WORLD.size),
    }


def _plan_path(name: str) -> Path:
    return RECORDS / f"{name}_h10_cell_degree_plan_v1.json"


def _authority_path(mpi_size: int) -> Path:
    return RECORDS / (
        f"legacy_seeded_plan_authority_mpi{mpi_size}_v1.json"
    )


def generate() -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    if comm.size not in {1, 2, 8}:
        raise RuntimeError("plan authority requires MPI1, MPI2, or MPI8")
    cfg = replace(
        target_stage4_config(degree=6, h_nm=10.0),
        case_name=f"task035d_plan_authority_mpi{comm.size}",
        unique_output=False,
    )
    with tempfile.TemporaryDirectory(
        prefix=f"task035d-plan-authority-mpi{comm.size}-",
    ) as directory:
        mesh_data = build_airbox_mesh_3d(
            cfg,
            Path(directory) / "mesh",
        )
        seed = load_legacy_multigoal_cell_seed(
            mesh_data.mesh,
            SEED,
        )
        plans: list[dict[str, Any]] = []
        for name, expected in TARGETS.items():
            proposal = build_legacy_seeded_variable_p_plan(
                mesh_data.mesh,
                seed,
                target_score_mass=float(expected["score_mass"]),
            )
            audit = proposal.audit
            observed = {
                "counts": dict(audit["cell_degree_counts"]),
                "active_fe_dofs": int(
                    audit["actual_conforming_active_fe_dofs"]
                ),
                "independent_trace_rows": int(
                    audit["periodic_independent_trace_rows"]
                ),
                "solve_rows": int(
                    audit["predicted_direct_solve_rows"]
                ),
                "plan_sha256": str(audit["cycle2_plan_sha256"]),
            }
            expected_observed = {
                key: expected[key]
                for key in (
                    "counts",
                    "active_fe_dofs",
                    "independent_trace_rows",
                    "solve_rows",
                    "plan_sha256",
                )
            }
            if observed != expected_observed:
                raise RuntimeError(
                    f"{name} plan differs from frozen authority: "
                    f"{observed}"
                )
            plan_path = _plan_path(name)
            if comm.size == 1:
                payload = variable_p_cell_degree_plan_payload(
                    mesh_data.mesh,
                    proposal.cycle2.cell_degree_by_box,
                    provenance={
                        "task": "Task035d",
                        "case_id": (
                            "097_goal_oriented_exact_sequence_hp_adaptivity"
                        ),
                        "selector": "legacy_multigoal_seed_v1",
                        "candidate": name,
                        "target_score_mass": expected["score_mass"],
                        "seed_payload_sha256": seed.payload_sha256,
                        "selector_audit": dict(audit),
                        "formal_accuracy_credit": False,
                        "fresh_12_channel_pde_required": True,
                        "ordinary_default_changed": False,
                    },
                )
                _write(plan_path, payload)
            comm.Barrier()
            if not plan_path.exists():
                raise RuntimeError(
                    f"{name} plan file must be generated by MPI1 first"
                )
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            if payload["cell_degree_plan_sha256"] != expected["plan_sha256"]:
                raise RuntimeError(f"{name} plan file has another identity")
            plans.append(
                {
                    "name": name,
                    "target_score_mass": expected["score_mass"],
                    "cell_degree_plan_sha256": expected["plan_sha256"],
                    "plan_file": str(plan_path.relative_to(ROOT)),
                    "plan_file_sha256": _sha256(plan_path),
                    "cell_degree_counts": observed["counts"],
                    "actual_conforming_active_fe_dofs": observed[
                        "active_fe_dofs"
                    ],
                    "periodic_independent_trace_rows": observed[
                        "independent_trace_rows"
                    ],
                    "predicted_direct_solve_rows": observed["solve_rows"],
                    "active_fe_dof_gate_pass": (
                        observed["active_fe_dofs"] <= 90_000
                    ),
                    "fresh_12_channel_pde_required": True,
                }
            )
    record = {
        "schema_version": (
            "task035d.legacy-seeded-plan-authority.v1"
        ),
        "status": (
            f"legacy_seeded_plan_authority_mpi{comm.size}_pass"
        ),
        "pass": True,
        "source": _source_identity(),
        "environment": _environment(),
        "geometry": "Task034 fixed rectangular block grating",
        "h_nm": 10.0,
        "degree_container": 6,
        "actual_axis_counts": [6, 3, 14],
        "cell_count": 252,
        "seed_payload_sha256": seed.payload_sha256,
        "seed_production_qualified": False,
        "plans": plans,
        "heavy_pde_started": False,
        "formal_accuracy_credit": False,
        "fresh_12_channel_pde_required": True,
        "ordinary_default_changed": False,
    }
    if comm.rank == 0:
        _write(_authority_path(comm.size), record)
    comm.Barrier()
    return record


def check() -> None:
    records = [_authority_path(size) for size in (1, 2, 8)]
    for path in records:
        if not path.exists():
            raise RuntimeError(f"missing plan authority: {path.name}")
    payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in records
    ]
    identities = [
        [
            (
                plan["name"],
                plan["cell_degree_plan_sha256"],
                plan["plan_file_sha256"],
                plan["actual_conforming_active_fe_dofs"],
                plan["periodic_independent_trace_rows"],
            )
            for plan in payload["plans"]
        ]
        for payload in payloads
    ]
    if len({json.dumps(value, sort_keys=True) for value in identities}) != 1:
        raise RuntimeError("MPI plan authorities disagree")
    print("Task035d legacy-seeded plan authorities: PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("generate", "check"),
        required=True,
    )
    args = parser.parse_args()
    if args.mode == "generate":
        generate()
    else:
        if MPI.COMM_WORLD.size != 1:
            raise RuntimeError("authority check is serial-only")
        check()


if __name__ == "__main__":
    main()
