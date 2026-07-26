#!/usr/bin/env python3
"""Independent checker for Task035d production local-h component records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[3]
CASE_DIR = Path(__file__).resolve().parent
RECORD_DIR = CASE_DIR / "records"
PLAN_RELATIVE = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "h15_top_air_local_h_plan_v1.json"
)
RECORD_NAMES = {
    1: "local_h_production_mpi1_v3_owner_gate_fix1.json",
    2: "local_h_production_mpi2_v3_owner_gate_fix1.json",
    8: "local_h_production_mpi8_v3_owner_gate_fix1.json",
}
OUTPUT_NAME = "local_h_production_mpi_identity_v3_owner_gate_fix1.json"
SCHEMA = "case097.local-h-production-component.v3-integration"
EXPECTED = {
    "root_cell_count": 120,
    "leaf_cell_count": 134,
    "hanging_patch_count": 6,
    "raw_broken_active_fe_dofs": 84_175,
    "raw_broken_trace_rows": 23_875,
    "hanging_slave_rows": 1_250,
    "periodic_slave_rows": 4_235,
    "actual_full3d_equivalent_active_fe_dofs": 82_925,
    "independent_trace_rows": 18_390,
    "predicted_direct_solve_rows": 18_470,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strict_load(path: Path) -> Mapping[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON constant {value}")
        ),
    )
    if not isinstance(payload, dict):
        raise TypeError("record root must be an object")
    return payload


def _commit_blob_sha(source_sha: str, relative: str) -> str:
    content = subprocess.check_output(
        ("git", "show", f"{source_sha}:{relative}"),
        cwd=ROOT,
    )
    return hashlib.sha256(content).hexdigest()


def _validate_one(path: Path, payload: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    try:
        mpi_size = int(payload["environment"]["mpi_size"])
        source_sha = str(payload["source_sha"])
        source = payload["source_identity"]
        stable = payload["stable_identity"]
        reduction = payload["reduction_audit"]
        trace = reduction["trace_constraints"]
        environment = payload["environment"]
        rank_rows = environment["rank_environments"]
        comparable = [
            {key: value for key, value in row.items() if key != "rank"}
            for row in rank_rows
        ]
        if path.name != RECORD_NAMES.get(mpi_size):
            failures.append("record_name")
        if payload.get("schema_version") != SCHEMA:
            failures.append("schema")
        if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
            failures.append("source_sha")
        if not (
            payload.get("pass") is True
            and payload.get("status") == "local_h_production_component_pass"
            and payload.get("heavy_pde_started") is False
            and payload.get("pde_accuracy_credit") is False
            and payload.get("ordinary_default_changed") is False
        ):
            failures.append("component_scope")
        if not (
            source.get("head") == source_sha
            and source.get("expected_sha") == source_sha
            and source.get("verified_clean_numerical_source") is True
        ):
            failures.append("source_identity")
        numerical = source.get("numerical_file_sha256")
        if not isinstance(numerical, dict) or not numerical:
            failures.append("numerical_manifest")
        elif any(
            _commit_blob_sha(source_sha, relative) != digest
            for relative, digest in numerical.items()
        ):
            failures.append("numerical_blob_identity")
        if not (
            environment.get("petsc_scalar_type") == "complex128"
            and environment.get("petsc_int_type") == "int32"
            and environment.get("all_ranks_identical") is True
            and len(rank_rows) == mpi_size
            and [row["rank"] for row in rank_rows] == list(range(mpi_size))
            and all(row == comparable[0] for row in comparable[1:])
        ):
            failures.append("mpi_abi")
        if payload["plan"]["path"] != PLAN_RELATIVE:
            failures.append("plan_path")
        plan_path = ROOT / PLAN_RELATIVE
        if (
            payload["plan"]["file_sha256"] != _sha256(plan_path)
            or payload["plan"]["payload"] != _strict_load(plan_path)
        ):
            failures.append("plan_identity")
        if any(int(stable.get(name, -1)) != expected for name, expected in EXPECTED.items()):
            failures.append("frozen_dimensions")
        if not (
            reduction.get("pass") is True
            and reduction.get("active_fe_dof_gate_pass") is True
            and trace.get("pass") is True
            and trace.get("constraint_kinds") == ["hanging", "floquet"]
            and trace.get("pde_launch_ownership_gate") is True
            and trace.get("inactive_p6_rows_globally_numbered") is False
        ):
            failures.append("production_reduction")
        checks = payload.get("checks")
        if not isinstance(checks, dict) or not checks or not all(checks.values()):
            failures.append("embedded_checks")
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        failures.append(f"exception:{type(exc).__name__}")
    return failures


def check_records(paths: tuple[Path, ...]) -> dict[str, Any]:
    payloads = [_strict_load(path) for path in paths]
    record_failures = {
        path.name: _validate_one(path, payload)
        for path, payload in zip(paths, payloads, strict=True)
    }
    failures = [
        f"{name}:{failure}"
        for name, row in record_failures.items()
        for failure in row
    ]
    sources = {str(payload.get("source_sha")) for payload in payloads}
    stable = [payload.get("stable_identity") for payload in payloads]
    numerical = [
        payload.get("source_identity", {}).get("numerical_file_sha256")
        for payload in payloads
    ]
    cross_checks = {
        "mpi_sizes_are_1_2_8": {
            int(payload["environment"]["mpi_size"])
            for payload in payloads
        }
        == {1, 2, 8},
        "same_source_sha": len(sources) == 1,
        "same_numerical_blobs": all(row == numerical[0] for row in numerical[1:]),
        "same_physical_identity": all(row == stable[0] for row in stable[1:]),
        "cross_rank_hanging_path_exercised": all(
            payload["reduction_audit"]["trace_constraints"][
                "cross_rank_hanging_patch_count"
            ]
            > 0
            for payload in payloads
            if int(payload["environment"]["mpi_size"]) > 1
        ),
        "no_heavy_pde_or_accuracy_credit": all(
            payload["heavy_pde_started"] is False
            and payload["pde_accuracy_credit"] is False
            for payload in payloads
        ),
    }
    failures.extend(
        f"cross:{name}"
        for name, passed in cross_checks.items()
        if not passed
    )
    source_sha = next(iter(sources)) if len(sources) == 1 else None
    live_head = subprocess.check_output(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        text=True,
    ).strip()
    return {
        "schema_version": (
            "case097.local-h-production-mpi-identity.v3-integration"
        ),
        "status": (
            "local_h_production_mpi_identity_pass"
            if not failures
            else "local_h_production_mpi_identity_fail"
        ),
        "pass": not failures,
        "candidate_id": "h15_top_air_local_h_v1",
        "source_sha": source_sha,
        "live_head": live_head,
        "input_records": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": _sha256(path),
                "mpi_size": int(payload["environment"]["mpi_size"]),
            }
            for path, payload in zip(paths, payloads, strict=True)
        ],
        "plan": {
            "path": PLAN_RELATIVE,
            "sha256": _sha256(ROOT / PLAN_RELATIVE),
        },
        "stable_identity": stable[0] if stable else None,
        "record_failures": record_failures,
        "cross_checks": cross_checks,
        "failures": failures,
        "pde_launch_gate": not failures,
        "pde_launch_scope": "one formal MPI8 h15 local-h direct PDE",
        "pde_accuracy_credit": False,
        "ordinary_default_changed": False,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--records",
        nargs=3,
        type=Path,
        required=True,
        metavar=("MPI1", "MPI2", "MPI8"),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    expected = tuple(
        (RECORD_DIR / RECORD_NAMES[size]).resolve()
        for size in (1, 2, 8)
    )
    paths = tuple(path.resolve() for path in args.records)
    if paths != expected:
        raise ValueError("formal inputs must be ordered MPI1/MPI2/MPI8 records")
    output = args.output.resolve()
    if output != (RECORD_DIR / OUTPUT_NAME).resolve():
        raise ValueError("formal MPI identity output path is fixed")
    if output.exists():
        raise FileExistsError("formal MPI identity record is immutable")
    result = check_records(paths)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                result,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
    print(
        json.dumps(
            {
                "output": str(output),
                "sha256": _sha256(output),
                "status": result["status"],
                "pass": result["pass"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
