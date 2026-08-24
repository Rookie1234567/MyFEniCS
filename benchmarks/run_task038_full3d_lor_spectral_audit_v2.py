"""Thin V11 S1 owner-space transfer/spectral audit runner.

This entry point only orchestrates the audit-only fixture and writes raw
artifacts.  It does not construct the production HX/PCGAMG path and does not
classify the result; the independent checker owns that decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from petsc4py import PETSc

from src.solvers.fullspace_lor_global_audit import (
    EIGEN_RESIDUAL_LIMIT,
    audit_fixture,
)
from src.solvers.fullspace_lor_native_hx_fixture import RealL2PositiveHXFixture


SCHEMA = "task038.lor-global-spectral-audit.v2"
BATCH_SCHEMA = "task038.lor-global-spectral-audit.v2.batch"
STAGE = "s1"
H_NM = 50.0
CASES = {"p2-mpi1": 2, "p3-mpi1": 3}
SOURCE_NAME = "random"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_array(raw_dir: Path, name: str, values: np.ndarray) -> dict[str, Any]:
    path = raw_dir / f"{name}.npy"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite raw artifact {path}")
    values = np.asarray(values)
    np.save(path, values, allow_pickle=False)
    return {
        "relative_path": path.name,
        "sha256": _sha256(path),
        "bytes": int(path.stat().st_size),
        "dtype": str(values.dtype),
        "shape": [int(item) for item in values.shape],
    }


def _write_csr(raw_dir: Path, name: str, matrix: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "rows": int(matrix["rows"]),
        "cols": int(matrix["cols"]),
        "nnz": int(matrix["nnz"]),
        "index_bytes": int(matrix["index_bytes"]),
        "numeric_bytes": int(matrix["numeric_bytes"]),
        "indptr": _write_array(raw_dir, f"{name}_indptr", matrix["indptr"]),
        "indices": _write_array(raw_dir, f"{name}_indices", matrix["indices"]),
        "values": _write_array(raw_dir, f"{name}_values", matrix["values"]),
    }


def _write_vector_list(raw_dir: Path, prefix: str, values: np.ndarray) -> list[dict[str, Any]]:
    values = np.asarray(values)
    return [_write_array(raw_dir, f"{prefix}_{index}", row) for index, row in enumerate(values)]


def _source_identity(repo: Path, expected_sha: str) -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "--git-dir=.git-codex", "--work-tree=.", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    status = git("status", "--short")
    if head != expected_sha:
        raise RuntimeError(f"source SHA mismatch: {head} != {expected_sha}")
    return {
        "expected_sha": expected_sha,
        "commit_sha_start": head,
        "branch": branch,
        "clean_start": not status,
        "tracked_status_start": status,
    }


def _source_probe(repo: Path, expected_sha: str) -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "--git-dir=.git-codex", "--work-tree=.", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    head = git("rev-parse", "HEAD")
    status = git("status", "--short")
    return {
        "commit_sha": head,
        "clean": not status,
        "tracked_status": status,
        "expected": head == expected_sha,
    }


def _write_marker(raw_dir: Path, name: str, **facts: Any) -> None:
    marker = raw_dir / "stage-rank0.jsonl"
    payload = {"stage": name, **_jsonable(facts)}
    with marker.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _runtime_facts(comm: Any) -> dict[str, Any]:
    return {
        "qualified_activation": os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION"),
        "mpi_size": int(comm.size),
        "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
        "petsc_int_type": str(np.dtype(PETSc.IntType)),
        "threads": {
            name: os.environ.get(name)
            for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
        },
    }


def _prepare_paths(raw_dir: Path, record_path: Path) -> None:
    if raw_dir.exists() or record_path.exists():
        raise FileExistsError("S1 worker paths must be fresh")
    raw_dir.mkdir(parents=True)


def _build_record(
    raw_dir: Path,
    record_path: Path,
    source: dict[str, Any],
    runtime: dict[str, Any],
    facts: dict[str, Any],
    command: list[str],
) -> dict[str, Any]:
    layout = facts["low_layout"]
    high_layout = facts["high_layout"]
    artifacts: dict[str, Any] = {
        "low_active_raw_rows": _write_array(raw_dir, "low_active_raw_rows", layout["active_raw_rows"]),
        "low_slave_raw_rows": _write_array(raw_dir, "low_slave_raw_rows", layout["slave_rows"]),
        "low_canonical_owner_ids": _write_array(raw_dir, "low_canonical_owner_ids", layout["canonical_ids"]),
        "low_topology_owner_ids": _write_array(
            raw_dir, "low_topology_owner_ids", layout["owner_ids"]
        ),
        "low_phase_codes": _write_array(raw_dir, "low_phase_codes", layout["phase_codes"]),
        "high_active_raw_rows": _write_array(raw_dir, "high_active_raw_rows", high_layout["active_raw_rows"]),
        "high_slave_raw_rows": _write_array(raw_dir, "high_slave_raw_rows", high_layout["slave_rows"]),
        "high_topology_owner_ids": _write_array(
            raw_dir, "high_topology_owner_ids", high_layout["owner_ids"]
        ),
        "singular_values": _write_array(raw_dir, "singular_values", facts["singular_values"]),
        "low_probes": _write_vector_list(raw_dir, "low_probe", facts["probes"]),
        "high_probes": _write_vector_list(raw_dir, "high_probe", facts["high_probes"]),
        "high_action_expected": _write_vector_list(raw_dir, "high_action_expected", facts["high_action_expected"]),
        "high_action_observed": _write_vector_list(raw_dir, "high_action_observed", facts["high_action_observed"]),
        "pull_expected": _write_vector_list(raw_dir, "pull_expected", facts["pull_expected"]),
        "pull_observed": _write_vector_list(raw_dir, "pull_observed", facts["pull_observed"]),
    }
    for index, payload in enumerate(facts["work_payload"]):
        for name, values in payload.items():
            artifacts[f"work_{index}_{name}"] = _write_array(raw_dir, f"work_{index}_{name}", values)
    matrices = {
        "B_L_full": _write_csr(raw_dir, "B_L_full", facts["low_matrix_full"]),
        "B_H_full": _write_csr(raw_dir, "B_H_full", facts["high_matrix_full"]),
        "B_L_ind": _write_csr(raw_dir, "B_L_ind", facts["low_matrix_ind"]),
        "B_H_ind": _write_csr(raw_dir, "B_H_ind", facts["high_matrix_ind"]),
        "L": _write_csr(raw_dir, "L", facts["transfer"]),
    }
    spectral: dict[str, Any] = {}
    for name in ("smallest", "largest"):
        item = facts["spectral"].get(name)
        if not isinstance(item, Mapping):
            continue
        spectral[name] = {
            key: value
            for key, value in item.items()
            if key not in ("vector", "Aq", "Bq")
        }
        for key in ("vector", "Aq", "Bq"):
            spectral[name][key] = _write_array(raw_dir, f"eigen_{name}_{key}", item[key])
    layout_artifacts = {
        name: artifacts[name]
        for name in (
            "low_active_raw_rows",
            "low_slave_raw_rows",
            "low_canonical_owner_ids",
            "low_topology_owner_ids",
            "low_phase_codes",
            "high_active_raw_rows",
            "high_slave_raw_rows",
            "high_topology_owner_ids",
        )
    }
    payload_artifacts = {
        name: value for name, value in artifacts.items() if name not in layout_artifacts
    }
    record = {
        "schema": SCHEMA,
        "stage": STAGE,
        "case": facts["case"],
        "degree": int(facts["settings"]["degree"]),
        "h_nm": H_NM,
        "source_name": SOURCE_NAME,
        "mpi_size": int(runtime["mpi_size"]),
        "raw_dir": str(raw_dir.resolve()),
        "record_path": str(record_path.resolve()),
        "command": command,
        "source": source,
        "runtime": runtime,
        "settings": _jsonable(facts["settings"]),
        "layout": {
            "low": {
                key: layout_artifacts[key]
                for key in (
                    "low_active_raw_rows",
                    "low_slave_raw_rows",
                    "low_canonical_owner_ids",
                    "low_topology_owner_ids",
                    "low_phase_codes",
                )
            },
            "high": {
                key: layout_artifacts[key]
                for key in (
                    "high_active_raw_rows",
                    "high_slave_raw_rows",
                    "high_topology_owner_ids",
                )
            },
            "tested_dimension": int(facts["tested_dimension"]),
            "numerical_rank": int(facts["numerical_rank"]),
            "rank_tau": float(facts["rank_tau"]),
            "low_owner_authority": layout["owner_authority"],
            "high_owner_authority": high_layout["owner_authority"],
            "low_bijection": bool(layout["bijection"]),
            "high_active_slave_partition": bool(high_layout["active_slave_partition"]),
            "independent_dimension_closed": bool(high_layout["independent_dimension_closed"]),
        },
        "matrix_artifacts": matrices,
        "artifacts": payload_artifacts,
        "spectral": spectral,
        "facts": {
            "spd": _jsonable(facts["spd"]),
            "spectral_status": facts["spectral"].get("status"),
        },
        "fixture_audit": _jsonable(facts["audit"]["fixture_audit"]),
        "fixture_hx_audit": _jsonable(facts["audit"]["fixture_hx_audit"]),
        "audit_assembly": {
            "high_order_global_aij": True,
            "sparse_independent_transfer": bool(
                facts["audit"]["sparse_independent_transfer"]
            ),
            "temporary_dense_transfer_for_rank_svd": bool(
                facts["audit"]["temporary_dense_transfer_for_rank_svd"]
            ),
            "production_global_dense_transfer": bool(
                facts["audit"]["production_global_dense_transfer"]
            ),
            "numeric_allgather": bool(facts["audit"]["global_numeric_allgather"]),
        },
        "forbidden": {
            "production_high_order_global_aij": bool(facts["audit"]["high_order_global_aij"]),
            "production_global_transfer_matrix": bool(facts["audit"]["global_transfer_matrix"]),
            "production_numeric_allgather": bool(facts["audit"]["global_numeric_allgather"]),
            "scalar_node_matrix_constructed": bool(facts["audit"]["fixture_hx_constructed"]),
            "native_hx_constructed": bool(facts["audit"]["fixture_hx_constructed"]),
        },
        "markers": {
            "relative_path": "stage-rank0.jsonl",
            "sha256": _sha256(raw_dir / "stage-rank0.jsonl"),
            "bytes": int((raw_dir / "stage-rank0.jsonl").stat().st_size),
            "lines": len(
                (raw_dir / "stage-rank0.jsonl").read_text(encoding="utf-8").splitlines()
            ),
        },
        "worker_facts_only": True,
    }
    return record


def _write_record(
    raw_dir: Path,
    record_path: Path,
    source: dict[str, Any],
    runtime: dict[str, Any],
    facts: dict[str, Any],
    command: list[str],
) -> None:
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record = _build_record(raw_dir, record_path, source, runtime, facts, command)
    record_path.write_text(
        json.dumps(record, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def run_worker(args: argparse.Namespace) -> int:
    from mpi4py import MPI

    if args.case not in (*CASES, "batch") or args.stage != STAGE or args.source_name != SOURCE_NAME:
        raise ValueError("S1 is fixed to p2/p3 MPI1 random cases")
    if int(args.expected_mpi_size) != 1 or MPI.COMM_WORLD.size != 1:
        raise ValueError("S1 runner requires MPI1")
    repo = Path(__file__).resolve().parents[1]
    raw_dir = Path(args.raw_dir).resolve()
    record_path = Path(args.record).resolve()
    command = [str(Path(sys.executable).resolve()), *sys.argv[1:]]
    if args.case == "batch":
        return run_batch(args, repo, raw_dir, record_path, command)
    _prepare_paths(raw_dir, record_path)
    _write_marker(
        raw_dir,
        "paths_ready",
        raw_dir=str(raw_dir),
        record_path=str(record_path),
    )
    source = _source_identity(repo, args.expected_source_sha)
    _write_marker(raw_dir, "source_runtime_closed", source=source)
    runtime = _runtime_facts(MPI.COMM_WORLD)
    fixture = None
    try:
        fixture = RealL2PositiveHXFixture(
            CASES[args.case], MPI.COMM_WORLD, variant="sequential-v1", build_hx=False
        )
        _write_marker(raw_dir, "fixture_built", degree=CASES[args.case], build_hx=False)
        facts = audit_fixture(fixture)
        facts["case"] = args.case
        _write_marker(
            raw_dir,
            "layout_closed",
            low_owner_count=facts["low_layout"]["owner_count"],
            high_owner_count=facts["high_layout"]["owner_count"],
        )
        _write_marker(
            raw_dir,
            "matrices_built",
            low_rows=facts["low_matrix_full"]["rows"],
            high_rows=facts["high_matrix_full"]["rows"],
        )
        _write_marker(
            raw_dir,
            "actions_checked",
            high_action_max=max(facts["high_action_relatives"]),
            work_max=max(facts["work_relatives"]),
            pull_max=max(facts["pull_relatives"]),
        )
        _write_marker(
            raw_dir,
            "rank_spd_checked",
            rank=facts["numerical_rank"],
            spd=facts["spd"],
        )
        _write_marker(
            raw_dir,
            "endpoints_solved"
            if facts["spectral"].get("status") == "solved"
            else "endpoints_not_run",
            spectral_status=facts["spectral"].get("status"),
        )
        end = _source_probe(repo, args.expected_source_sha)
        source.update(
            {
                "commit_sha_end": end["commit_sha"],
                "clean_end": end["clean"],
                "tracked_status_end": end["tracked_status"],
            }
        )
        if not end["expected"]:
            raise RuntimeError("source SHA changed before record closeout")
        _write_marker(raw_dir, "record_written", source_end=end)
        _write_record(
            raw_dir,
            record_path,
            source,
            runtime,
            facts,
            command,
        )
    finally:
        if fixture is not None:
            fixture.destroy()
    return 0


def _batch_case_is_closed(facts: Mapping[str, Any]) -> bool:
    if facts["spectral"].get("status") != "solved":
        return False
    if facts["numerical_rank"] != facts["tested_dimension"]:
        return False
    if not all(bool(item.get("positive_definite")) for item in facts["spd"].values()):
        return False
    if max(facts["high_action_relatives"]) > HIGH_ACTION_LIMIT:
        return False
    if max(facts["work_relatives"]) > WORK_LIMIT:
        return False
    if max(facts["pull_relatives"]) > WORK_LIMIT:
        return False
    if max(facts["hermitian_defects"].values()) > WORK_LIMIT:
        return False
    smallest = facts["spectral"]["smallest"]
    largest = facts["spectral"]["largest"]
    lambda_min = float(smallest["eigenvalue"])
    lambda_max = float(largest["eigenvalue"])
    threshold = (
        max(float(facts["tested_dimension"]) * np.finfo(float).eps * lambda_max, 0.0)
        if np.isfinite(lambda_max)
        else math.inf
    )
    condition = facts.get("condition")
    if (
        not np.isfinite(lambda_min)
        or not np.isfinite(lambda_max)
        or lambda_min <= threshold
        or lambda_max < lambda_min
        or not isinstance(condition, (int, float))
        or not np.isfinite(float(condition))
        or smallest["residual_relative"] > EIGEN_RESIDUAL_LIMIT
        or largest["residual_relative"] > EIGEN_RESIDUAL_LIMIT
    ):
        return False
    return True


def _release_batch_case(
    fixture: Any | None, facts: dict[str, Any] | None
) -> tuple[Any | None, None]:
    if fixture is not None:
        fixture.destroy()
        fixture = None
    if facts is not None:
        facts.clear()
    return fixture, None


def run_batch(
    args: argparse.Namespace,
    repo: Path,
    raw_dir: Path,
    record_path: Path,
    command: list[str],
) -> int:
    from mpi4py import MPI

    _prepare_paths(raw_dir, record_path)
    source = _source_identity(repo, args.expected_source_sha)
    runtime = _runtime_facts(MPI.COMM_WORLD)
    case_records: list[dict[str, Any]] = []
    not_run: list[str] = []
    stop_reason: str | None = None
    for case_name in ("p2-mpi1", "p3-mpi1"):
        case_raw = raw_dir / case_name
        _prepare_paths(case_raw, record_path)
        _write_marker(case_raw, "paths_ready", worker_raw_dir=str(case_raw), record_path=str(record_path))
        _write_marker(case_raw, "source_runtime_closed", source=source)
        fixture = None
        facts: dict[str, Any] | None = None
        try:
            fixture = RealL2PositiveHXFixture(
                CASES[case_name],
                MPI.COMM_WORLD,
                variant="sequential-v1",
                build_hx=False,
            )
            _write_marker(case_raw, "fixture_built", degree=CASES[case_name], build_hx=False)
            facts = audit_fixture(fixture)
            facts["case"] = case_name
            _write_marker(
                case_raw,
                "layout_closed",
                low_owner_count=facts["low_layout"]["owner_count"],
                high_owner_count=facts["high_layout"]["owner_count"],
            )
            _write_marker(
                case_raw,
                "matrices_built",
                low_rows=facts["low_matrix_full"]["rows"],
                high_rows=facts["high_matrix_full"]["rows"],
            )
            _write_marker(
                case_raw,
                "actions_checked",
                high_action_max=max(facts["high_action_relatives"]),
                work_max=max(facts["work_relatives"]),
                pull_max=max(facts["pull_relatives"]),
            )
            _write_marker(case_raw, "rank_spd_checked", rank=facts["numerical_rank"], spd=facts["spd"])
            _write_marker(
                case_raw,
                "endpoints_solved"
                if facts["spectral"].get("status") == "solved"
                else "endpoints_not_run",
                spectral_status=facts["spectral"].get("status"),
            )
            _write_marker(case_raw, "record_written", case=case_name)
            case_records.append(_build_record(case_raw, record_path, source, runtime, facts, command))
            continue_case = _batch_case_is_closed(facts)
        finally:
            fixture, facts = _release_batch_case(fixture, facts)
        if not continue_case:
            stop_reason = f"prior_case_gate_facts:{case_name}"
            not_run.extend(
                name
                for name in ("p2-mpi1", "p3-mpi1")
                if name not in [item["case"] for item in case_records]
            )
            break
    completed_names = [item["case"] for item in case_records]
    not_run.extend(
        name
        for name in ("p2-mpi1", "p3-mpi1")
        if name not in completed_names and name not in not_run
    )
    end = _source_probe(repo, args.expected_source_sha)
    source.update(
        {
            "commit_sha_end": end["commit_sha"],
            "clean_end": end["clean"],
            "tracked_status_end": end["tracked_status"],
        }
    )
    if not end["expected"]:
        raise RuntimeError("source SHA changed before batch record closeout")
    _write_marker(raw_dir, "batch_record_written", completed=list(completed_names), not_run=not_run)
    batch_record = {
        "schema": BATCH_SCHEMA,
        "stage": STAGE,
        "case": "batch",
        "source_name": SOURCE_NAME,
        "mpi_size": int(runtime["mpi_size"]),
        "raw_dir": str(raw_dir),
        "record_path": str(record_path),
        "command": command,
        "source": source,
        "runtime": runtime,
        "cases": case_records,
        "completed_cases": [item["case"] for item in case_records],
        "not_run_cases": not_run,
        "stop_reason": stop_reason,
        "worker_facts_only": True,
    }
    batch_record["markers"] = {
        "relative_path": "stage-rank0.jsonl",
        "sha256": _sha256(raw_dir / "stage-rank0.jsonl"),
        "bytes": int((raw_dir / "stage-rank0.jsonl").stat().st_size),
        "lines": len((raw_dir / "stage-rank0.jsonl").read_text(encoding="utf-8").splitlines()),
    }
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        json.dumps(batch_record, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=(STAGE,))
    parser.add_argument("--case", required=True, choices=(*CASES, "batch"))
    parser.add_argument("--source-name", default=SOURCE_NAME, choices=(SOURCE_NAME,))
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", required=True, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return run_worker(args)


if __name__ == "__main__":
    raise SystemExit(main())
