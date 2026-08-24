"""Thin V11 S2 p6/h10 memory-first foundation worker.

The external foundation watchdog owns the cold process-tree resource Gate.
This worker owns only the p6 mesh/actions, a fixed restart-20 reserve, ten
scalar-only apply rounds, and a compact record.  It never builds the old HX,
nodal, coarse, or global high-order matrix paths.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping

import numpy as np

from src.solvers.fullspace_lor_memory_first_foundation import (
    S2_APPLY_NAMES,
    S2_DEGREE,
    S2_H_NM,
    S2_REPEAT_COUNT,
    S2_RETAINED_RSS_LIMIT,
    S2_RESERVE_VECTOR_COUNT,
    S2_SCHEMA,
    S2_WAVELENGTH_NM,
    allocate_restart20_reserve,
    build_s2_foundation_case,
    destroy_restart20_reserve,
    run_fixed_apply_ledger,
)
from benchmarks.run_task038_full3d_t3 import (
    T3_EXPECTED_INPUT_BYTES,
    T3_EXPECTED_INPUT_SHA256,
    T3_EXPECTED_PHYSICAL_MODEL_SHA256,
    T3_EXPECTED_RESOLVED_CONFIG_BYTES,
    T3_EXPECTED_RESOLVED_CONFIG_SHA256,
    T3_TEMPLATE_RELATIVE_PATH,
)


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
STAGE = "s2"
CASE = "p6-h10-mpi1"
MODULE = "benchmarks.run_task038_full3d_lor_s2_memory_first"
RETAINED_DWELL_SECONDS = 2.0
MARKERS = (
    "paths_ready",
    "source_runtime_closed",
    "fixture_built",
    "reserve_built",
    "apply_ledger_written",
    "retained_ready",
    "record_written",
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    return str(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "--git-dir=.git-codex", "--work-tree=.", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git identity probe failed")
    return result.stdout.strip()


def _source_identity(root: Path, expected_sha: str) -> dict[str, Any]:
    actual = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    status = _git(root, "status", "--short", "--untracked-files=all")
    if actual != expected_sha or branch != BRANCH or status:
        raise RuntimeError(
            f"source not closed: sha={actual}, branch={branch}, status={status!r}"
        )
    return {
        "expected_sha": expected_sha,
        "commit_sha": actual,
        "branch": branch,
        "clean": not bool(status),
        "tracked_status": status,
    }


def _runtime(root: Path, expected_sha: str, comm: Any) -> dict[str, Any]:
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("qualified activation marker is not 1")
    executable = Path(sys.executable).absolute()
    if executable.parent.resolve() != (root / ".venv" / "bin").resolve():
        raise RuntimeError(f"qualified repository Python required, got {executable}")
    threads = {
        name: os.environ.get(name)
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    }
    if any(value not in (None, "1") for value in threads.values()):
        raise RuntimeError(f"threads are not fixed to one: {threads}")
    from petsc4py import PETSc

    scalar = np.dtype(PETSc.ScalarType)
    integer = np.dtype(PETSc.IntType)
    if scalar != np.dtype(np.complex128) or integer != np.dtype(np.int32):
        raise RuntimeError(f"ABI dtype mismatch: {scalar}/{integer}")
    return {
        "qualified_activation": "1",
        "sys_executable": str(executable),
        "mpi_size": int(comm.size),
        "petsc_scalar_type": str(PETSc.ScalarType),
        "petsc_int_type": str(PETSc.IntType),
        "scalar_dtype": str(scalar),
        "int_dtype": str(integer),
        "threads": threads,
        "source": _source_identity(root, expected_sha),
    }


def _prepare_paths(raw_dir: Path, record_path: Path, comm: Any) -> None:
    failure = None
    if comm.rank == 0:
        try:
            if raw_dir.exists() or record_path.exists():
                raise FileExistsError("S2 raw_dir or record already exists")
            raw_dir.mkdir(parents=True)
            (raw_dir / "markers").mkdir()
        except (FileExistsError, OSError) as exc:
            failure = (type(exc).__name__, str(exc))
    failure = comm.bcast(failure, root=0)
    if failure is not None:
        raise FileExistsError(failure[1]) if failure[0] == "FileExistsError" else OSError(failure[1])
    comm.barrier()


def _marker(raw_dir: Path, name: str, source_sha: str, comm: Any, **facts: Any) -> int:
    if name not in MARKERS:
        raise ValueError(f"unknown S2 marker {name}")
    wall_time_ns = time.time_ns() if comm.rank == 0 else None
    wall_time_ns = comm.bcast(wall_time_ns, root=0)
    if comm.rank == 0:
        path = raw_dir / "markers" / f"{name}.json"
        path.write_bytes(
            json.dumps(
                {
                    "schema": "task038.full3d.lor-memory-first.s2-marker.v1",
                    "marker": name,
                    "source_sha": source_sha,
                    "wall_time_ns": int(wall_time_ns),
                    "facts": _jsonable(facts),
                },
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
    comm.barrier()
    return int(wall_time_ns)


def _resource_sample() -> dict[str, Any]:
    from benchmarks.task034_wsl_resources import resource_authority_sample

    return resource_authority_sample(os.getpid())


def _vector_digest(vector: Any) -> str:
    payload = np.ascontiguousarray(
        np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    ).view(np.uint8)
    return hashlib.sha256(payload).hexdigest()


def _vector_fact(vector: Any) -> dict[str, Any]:
    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    return {
        "finite": bool(np.all(np.isfinite(values))),
        "norm": float(vector.norm()),
        "digest": hashlib.sha256(np.ascontiguousarray(values).view(np.uint8)).hexdigest(),
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    path.write_bytes(encoded + b"\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _input_identity(
    root: Path, input_path: Path, specification: Any, resolved: bytes
) -> dict[str, Any]:
    template = (root / T3_TEMPLATE_RELATIVE_PATH).resolve()
    actual = input_path.resolve()
    if actual != template:
        raise RuntimeError(
            "S2 uses the frozen Task38 template input: "
            f"expected={template}, actual={actual}"
        )
    raw = bytes(specification.raw_input_bytes)
    resolved_bytes = bytes(resolved)
    raw_sha = hashlib.sha256(raw).hexdigest()
    resolved_sha = hashlib.sha256(resolved_bytes).hexdigest()
    if (
        len(raw) != T3_EXPECTED_INPUT_BYTES
        or raw_sha != T3_EXPECTED_INPUT_SHA256
        or len(resolved_bytes) != T3_EXPECTED_RESOLVED_CONFIG_BYTES
        or resolved_sha != T3_EXPECTED_RESOLVED_CONFIG_SHA256
        or str(specification.physical_model_sha256)
        != T3_EXPECTED_PHYSICAL_MODEL_SHA256
    ):
        raise RuntimeError("S2 frozen input/resolved/physical identity changed")
    return {
        "path_absolute": str(actual),
        "path_relative": T3_TEMPLATE_RELATIVE_PATH,
        "raw_bytes": len(raw),
        "raw_sha256": raw_sha,
        "physical_model_sha256": str(specification.physical_model_sha256),
        "resolved_bytes": len(resolved_bytes),
        "resolved_sha256": resolved_sha,
    }


def run_worker_with_input(
    raw_dir: Path,
    record_path: Path,
    input_path: Path,
    expected_sha: str,
    expected_mpi: int,
) -> None:
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    if comm.size != int(expected_mpi) or comm.size != 1:
        raise RuntimeError("S2 foundation is fixed to MPI1")
    root = Path(__file__).resolve().parents[1]
    raw_dir = raw_dir if raw_dir.is_absolute() else root / raw_dir
    record_path = record_path if record_path.is_absolute() else root / record_path
    input_path = input_path if input_path.is_absolute() else root / input_path
    raw_dir = raw_dir.resolve()
    record_path = record_path.resolve()
    input_path = input_path.resolve()
    _prepare_paths(raw_dir, record_path, comm)
    _marker(raw_dir, "paths_ready", expected_sha, comm, raw_dir=str(raw_dir.resolve()))
    runtime = _runtime(root, expected_sha, comm)
    _marker(raw_dir, "source_runtime_closed", expected_sha, comm, runtime=runtime)

    case = None
    reserve = None
    try:
        from benchmarks.run_task038_full3d_r4 import _resolve_case

        specification, cfg, resolved = _resolve_case(
            root, input_path, S2_DEGREE, S2_H_NM
        )
        input_identity = _input_identity(root, input_path, specification, resolved)
        case = build_s2_foundation_case(
            raw_dir,
            comm,
            cfg,
            resolved_config=resolved,
            resource_sample=_resource_sample,
        )
        _marker(raw_dir, "fixture_built", expected_sha, comm, audit=case.audit)
        reserve = allocate_restart20_reserve(case.high_primal_source)
        _marker(raw_dir, "reserve_built", expected_sha, comm, reserve={k: v for k, v in reserve.items() if k != "vectors"})
        input_vectors = {
            "high_primal": case.high_primal_source,
            "high_dual": case.high_dual_source,
            "low_primal": case.low_primal_source,
        }
        input_before = {
            name: _vector_digest(vector) for name, vector in input_vectors.items()
        }
        operations = (
            ("high_positive", lambda: (case.high_positive_into(case.high_primal_source, case.high_work_output), _vector_fact(case.high_work_output))[1]),
            ("physical_volume_dtn", lambda: (case.physical_into(case.high_primal_source, case.high_work_output), _vector_fact(case.high_work_output))[1]),
            ("restrict_high_to_lor", lambda: (case.restrict_into(case.high_dual_source, case.low_work_input), _vector_fact(case.low_work_input))[1]),
            ("lor_edge_matvec", lambda: (case.lor_matvec_into(case.low_primal_source, case.low_work_output), _vector_fact(case.low_work_output))[1]),
            ("lift_lor_to_high", lambda: (case.lift_into(case.low_primal_source, case.high_work_output), _vector_fact(case.high_work_output))[1]),
        )
        ledger = run_fixed_apply_ledger(operations, resource_sample=_resource_sample)
        del operations
        input_after = {
            name: _vector_digest(vector) for name, vector in input_vectors.items()
        }
        raw_ledger = raw_dir / "apply_ledger.json"
        ledger_sha = _write_json(raw_ledger, ledger)
        _marker(raw_dir, "apply_ledger_written", expected_sha, comm, ledger_sha256=ledger_sha)
        gc.collect()
        retained_ready_wall_time_ns = _marker(
            raw_dir,
            "retained_ready",
            expected_sha,
            comm,
            retained_dwell_seconds=RETAINED_DWELL_SECONDS,
            resource_authority="external_foundation_watchdog",
        )
        time.sleep(RETAINED_DWELL_SECONDS)
        resource = _resource_sample()
        retained = case.retained_ledger(reserve, resource)
        end_source = _source_identity(root, expected_sha)
        resolved_bytes = (
            resolved if isinstance(resolved, bytes) else str(resolved).encode("utf-8")
        )
        record = {
            "schema": S2_SCHEMA,
            "stage": STAGE,
            "case": CASE,
            "degree": S2_DEGREE,
            "h_nm": S2_H_NM,
            "wavelength_nm": S2_WAVELENGTH_NM,
            "mpi_size": int(comm.size),
            "raw_dir": str(raw_dir.resolve()),
            "record_path": str(record_path.resolve()),
            "command": [
                str(Path(sys.executable).absolute()), "-m", MODULE,
                "--stage", STAGE, "--case", CASE, "--raw-dir", str(raw_dir.resolve()),
                "--record", str(record_path.resolve()), "--expected-source-sha", expected_sha,
                "--expected-mpi-size", str(expected_mpi), "--input", str(input_path.resolve()),
            ],
            "source": {"start": runtime["source"], "end": end_source},
            "runtime": runtime,
            "settings": {
                "apply_names": list(S2_APPLY_NAMES),
                "repeat_count": S2_REPEAT_COUNT,
                "restart_basis_count": 21,
                "auxiliary_vector_count": 4,
                "reserve_vector_count": S2_RESERVE_VECTOR_COUNT,
                "restart_semantics": "21 basis + solution/rhs/residual/action; solution reserve only, no iteration history",
                "retained_rss_limit_bytes": S2_RETAINED_RSS_LIMIT,
                "cold_rss_limit_bytes": 1_800_000_000,
                "repeat_growth_limit_bytes": 32_000_000,
            },
            "provenance": {
                "model": "p6/h10/13.5nm rectangular-block foundation",
                "source_identity_sha256": hashlib.sha256(expected_sha.encode()).hexdigest(),
                "mode_manifest_sha256": case.mode_sha,
                "resolved_input_sha256": hashlib.sha256(resolved_bytes).hexdigest(),
                "physical_model_sha256": input_identity["physical_model_sha256"],
            },
            "input_identity": input_identity,
            "architecture": case.audit,
            "reserve": {k: v for k, v in reserve.items() if k != "vectors"},
            "apply_ledger": {"relative_path": raw_ledger.name, "sha256": ledger_sha, **ledger},
            "input_facts": {
                name: {
                    "before_digest": input_before[name],
                    "after_digest": input_after[name],
                    "unchanged": input_before[name] == input_after[name],
                }
                for name in input_vectors
            },
            "retained_ready_wall_time_ns": retained_ready_wall_time_ns,
            "retained_dwell_seconds": RETAINED_DWELL_SECONDS,
            "resource_authority": "external_foundation_watchdog_process_tree_for_cold_and_retained_peaks",
            "markers": {"relative_dir": "markers", "names": list(MARKERS)},
            "retained": retained,
        }
        if comm.rank == 0:
            _write_json(record_path, record)
        comm.barrier()
        _marker(raw_dir, "record_written", expected_sha, comm, record_path=str(record_path.resolve()))
    finally:
        if reserve is not None:
            destroy_restart20_reserve(reserve)
        if case is not None:
            case.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=(STAGE,), required=True)
    parser.add_argument("--case", choices=(CASE,), required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    run_worker_with_input(
        args.raw_dir,
        args.record,
        args.input,
        args.expected_source_sha,
        args.expected_mpi_size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
