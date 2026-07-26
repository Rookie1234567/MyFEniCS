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
DEFAULT_CANDIDATE_ID = "h15_top_air_local_h_v1"
CHECKER_RELATIVE = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/"
    "check_local_h_production_authority.py"
)
CANDIDATE_SPECS = {
    DEFAULT_CANDIDATE_ID: {
        "plan_relative": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
            "h15_top_air_local_h_plan_v1.json"
        ),
        "record_names": {
            1: "local_h_production_mpi1_v3_owner_gate_fix1.json",
            2: "local_h_production_mpi2_v3_owner_gate_fix1.json",
            8: "local_h_production_mpi8_v3_owner_gate_fix1.json",
        },
        "output_name": (
            "local_h_production_mpi_identity_v3_owner_gate_fix2.json"
        ),
        "schema": "case097.local-h-production-component.v3-integration",
        "pass_status": "local_h_production_component_pass",
        "identity_schema": (
            "case097.local-h-production-mpi-identity.v3-integration"
        ),
        "identity_status": "local_h_production_mpi_identity_pass",
        "pde_launch_scope": "one formal MPI8 h15 local-h direct PDE",
        "expected": {
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
        },
        "variable_interior": False,
    },
    "h15_symmetric_top_air_remote_p5_interior_v1": {
        "plan_relative": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
            "h15_symmetric_top_air_remote_p5_interior_plan_v1.json"
        ),
        "record_names": {
            1: "combined_hp_interior_mpi1_v1.json",
            2: "combined_hp_interior_mpi2_v1.json",
            8: "combined_hp_interior_mpi8_v1.json",
        },
        "output_name": "combined_hp_interior_mpi_identity_v1.json",
        "schema": "case097.combined-hp-interior-component.v1",
        "pass_status": "combined_hp_interior_component_pass",
        "identity_schema": (
            "case097.combined-hp-interior-mpi-identity.v1"
        ),
        "identity_status": "combined_hp_interior_mpi_identity_pass",
        "pde_launch_scope": (
            "one formal MPI8 h15 symmetric local-h plus "
            "variable-interior direct PDE"
        ),
        "expected": {
            "root_cell_count": 120,
            "leaf_cell_count": 148,
            "hanging_patch_count": 12,
            "raw_broken_active_fe_dofs": 86_740,
            "raw_broken_trace_rows": 26_860,
            "hanging_slave_rows": 2_500,
            "periodic_slave_rows": 4_380,
            "actual_full3d_equivalent_active_fe_dofs": 84_240,
            "independent_trace_rows": 19_980,
            "predicted_direct_solve_rows": 20_060,
        },
        "variable_interior": True,
    },
}


def _candidate_spec(candidate_id: str) -> Mapping[str, Any]:
    try:
        return CANDIDATE_SPECS[str(candidate_id)]
    except KeyError as exc:
        raise ValueError(f"unknown Task035d candidate {candidate_id!r}") from exc


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


def _validate_one(
    path: Path,
    payload: Mapping[str, Any],
    *,
    candidate_id: str,
    spec: Mapping[str, Any],
) -> list[str]:
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
        if path.name != spec["record_names"].get(mpi_size):
            failures.append("record_name")
        if payload.get("schema_version") != spec["schema"]:
            failures.append("schema")
        if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
            failures.append("source_sha")
        if not (
            payload.get("pass") is True
            and payload.get("status") == spec["pass_status"]
            and payload.get("candidate_id") == candidate_id
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
        plan_relative = str(spec["plan_relative"])
        if payload["plan"]["path"] != plan_relative:
            failures.append("plan_path")
        plan_path = ROOT / plan_relative
        if (
            payload["plan"]["file_sha256"] != _sha256(plan_path)
            or payload["plan"]["payload"] != _strict_load(plan_path)
        ):
            failures.append("plan_identity")
        if any(
            int(stable.get(name, -1)) != expected
            for name, expected in spec["expected"].items()
        ):
            failures.append("frozen_dimensions")
        if not (
            reduction.get("pass") is True
            and reduction.get("active_fe_dof_gate_pass") is True
            and trace.get("pass") is True
            and trace.get("constraint_kinds") == ["hanging", "floquet"]
            and trace.get("pde_launch_ownership_gate") is True
            and trace.get(
                "hanging_or_floquet_slave_rows_globally_numbered"
            )
            is False
        ):
            failures.append("production_reduction")
        if spec["variable_interior"] and not (
            reduction["degree_plan"].get("cell_degree_counts")
            == {"p4": 0, "p5": 32, "p6": 116}
            and reduction["degree_plan"].get(
                "local_variable_trace_implemented"
            )
            is False
            and reduction["degree_plan"].get(
                "complete_combined_hp_credit"
            )
            is False
            and stable.get("cell_degree_counts")
            == {"p4": 0, "p5": 32, "p6": 116}
            and isinstance(stable.get("cell_degree_plan_sha256"), str)
            and isinstance(
                stable.get("canonical_degree_map_sha256"),
                str,
            )
        ):
            failures.append("variable_interior_scope")
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


def check_records(
    paths: tuple[Path, ...],
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
) -> dict[str, Any]:
    spec = _candidate_spec(candidate_id)
    payloads = [_strict_load(path) for path in paths]
    record_failures = {
        path.name: _validate_one(
            path,
            payload,
            candidate_id=candidate_id,
            spec=spec,
        )
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
    distributed = [
        payload
        for payload in payloads
        if int(payload["environment"]["mpi_size"]) > 1
    ]
    zero_cross_rank = [
        payload
        for payload in distributed
        if payload["reduction_audit"]["trace_constraints"][
            "cross_rank_hanging_patch_count"
        ]
        == 0
    ]
    positive_cross_rank = [
        payload
        for payload in distributed
        if payload["reduction_audit"]["trace_constraints"][
            "cross_rank_hanging_patch_count"
        ]
        > 0
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
        "rank_local_and_cross_rank_hanging_partitions_qualified": (
            bool(zero_cross_rank)
            and bool(positive_cross_rank)
            and all(
                payload["reduction_audit"]["trace_constraints"][
                    "pde_launch_ownership_gate"
                ]
                is True
                for payload in distributed
            )
            and all(
                sum(
                    payload["reduction_audit"]["trace_constraints"][
                        "owner_routed_trace_cache_audit"
                    ]["request_counts_by_rank"]
                )
                > 0
                for payload in zero_cross_rank
            )
            and all(
                sum(
                    payload["reduction_audit"]["trace_constraints"][
                        "cross_rank_hanging_remote_lookup_counts_by_rank"
                    ]
                )
                > 0
                for payload in positive_cross_rank
            )
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
    checker_status = subprocess.check_output(
        (
            "git",
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            CHECKER_RELATIVE,
        ),
        cwd=ROOT,
        text=True,
    ).strip()
    checker_live_sha256 = _sha256(Path(__file__))
    checker_committed_sha256 = _commit_blob_sha(
        live_head,
        CHECKER_RELATIVE,
    )
    checker_identity = {
        "path": CHECKER_RELATIVE,
        "source_sha": live_head,
        "live_sha256": checker_live_sha256,
        "committed_sha256": checker_committed_sha256,
        "status_lines": checker_status.splitlines(),
        "verified_clean_checker": (
            checker_live_sha256 == checker_committed_sha256
            and not checker_status
        ),
    }
    if checker_identity["verified_clean_checker"] is not True:
        failures.append("checker_source_identity")
    return {
        "schema_version": (
            spec["identity_schema"]
        ),
        "status": (
            spec["identity_status"]
            if not failures
            else f"{spec['identity_status']}_failed"
        ),
        "pass": not failures,
        "candidate_id": candidate_id,
        "source_sha": source_sha,
        "live_head": live_head,
        "checker_identity": checker_identity,
        "input_records": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": _sha256(path),
                "mpi_size": int(payload["environment"]["mpi_size"]),
            }
            for path, payload in zip(paths, payloads, strict=True)
        ],
        "plan": {
            "path": spec["plan_relative"],
            "sha256": _sha256(ROOT / str(spec["plan_relative"])),
        },
        "stable_identity": stable[0] if stable else None,
        "record_failures": record_failures,
        "cross_checks": cross_checks,
        "failures": failures,
        "pde_launch_gate": not failures,
        "pde_launch_scope": spec["pde_launch_scope"],
        "pde_accuracy_credit": False,
        "ordinary_default_changed": False,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate",
        choices=tuple(CANDIDATE_SPECS),
        default=DEFAULT_CANDIDATE_ID,
    )
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
    spec = _candidate_spec(args.candidate)
    expected = tuple(
        (RECORD_DIR / spec["record_names"][size]).resolve()
        for size in (1, 2, 8)
    )
    paths = tuple(path.resolve() for path in args.records)
    if paths != expected:
        raise ValueError("formal inputs must be ordered MPI1/MPI2/MPI8 records")
    output = args.output.resolve()
    if output != (RECORD_DIR / str(spec["output_name"])).resolve():
        raise ValueError("formal MPI identity output path is fixed")
    if output.exists():
        raise FileExistsError("formal MPI identity record is immutable")
    result = check_records(paths, candidate_id=args.candidate)
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
