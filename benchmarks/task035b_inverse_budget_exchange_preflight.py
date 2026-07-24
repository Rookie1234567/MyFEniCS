"""Exclusive clean-SHA wrapper for the inverse budget-exchange audit.

The command is deliberately serial and structural.  It never builds a mesh,
compiles a form, launches an MPI solve, assembles a matrix, or runs a PDE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Mapping

import basix
from mpi4py import MPI
import mpi4py
import numpy as np
from petsc4py import PETSc
import petsc4py

from src.adaptivity.inverse_trace_interior_budget_audit import (
    audit_inverse_trace_interior_budget_exchange,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = (
    "codex/20260723-task35b-high-order-local-hp-resource-envelope"
)
RECORDS = (
    ROOT
    / "benchmarks/cases/095_high_order_local_hp_resource_envelope/records"
)
DEFAULT_OUTPUT = Path(
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/records/"
    "inverse_trace_interior_budget_exchange_preflight.json"
)
SOURCE_FILES = (
    "benchmarks/task035b_inverse_budget_exchange_preflight.py",
    "src/adaptivity/inverse_trace_interior_budget_audit.py",
    "src/adaptivity/hcurl_regionwise_p.py",
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


def _is_full_sha(value: str) -> bool:
    return len(value) == 40 and all(
        character in "0123456789abcdef"
        for character in value.lower()
    )


def _source_file_hashes(repo_root: Path) -> dict[str, str]:
    result = {}
    for relative in SOURCE_FILES:
        path = repo_root / relative
        if not path.is_file():
            raise RuntimeError(f"required source file is missing: {relative}")
        result[relative] = _sha256(path)
    return result


def _verified_source_identity(
    repo_root: Path,
    verified_clean_sha: str,
) -> dict[str, Any]:
    verified = str(verified_clean_sha).strip().lower()
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    checks = {
        "full_verified_sha": _is_full_sha(verified),
        "head_matches_verified_sha": head == verified,
        "expected_branch": branch == EXPECTED_BRANCH,
        "tracked_and_untracked_worktree_clean": status == "",
    }
    if not all(checks.values()):
        raise SystemExit(
            "inverse budget-exchange source gate failed: "
            + ", ".join(
                name for name, passed in checks.items() if not passed
            )
        )
    return {
        "commit_sha": head,
        "verified_clean_sha": verified,
        "branch": branch,
        "tracked_source_dirty": False,
        "status_before": status,
        "stable_and_clean_before": True,
        "source_files_sha256_before": _source_file_hashes(repo_root),
        "checks": checks,
    }


def _close_source_identity(
    repo_root: Path,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    hashes_after = _source_file_hashes(repo_root)
    checks = {
        "head_stable_after_build": head == source["commit_sha"],
        "branch_stable_after_build": branch == source["branch"],
        "worktree_still_clean_before_exclusive_write": status == "",
        "source_files_stable_after_build": (
            hashes_after == source["source_files_sha256_before"]
        ),
    }
    if not all(checks.values()):
        raise SystemExit(
            "inverse budget-exchange source closure failed: "
            + ", ".join(
                name for name, passed in checks.items() if not passed
            )
        )
    return {
        **dict(source),
        "head_after_build": head,
        "status_after_build_before_write": status,
        "source_files_sha256_after": hashes_after,
        "stable_and_clean_after_build": True,
        "closure_checks": checks,
    }


def _environment_identity(repo_root: Path) -> dict[str, Any]:
    executable = Path(sys.executable).resolve()
    expected_python = (repo_root / ".venv/bin/python").resolve()
    checks = {
        "qualified_activation_marker": (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
        ),
        "repo_virtualenv_python": executable == expected_python,
        "linux_runtime": sys.platform.startswith("linux"),
        "complex128_petsc": np.dtype(PETSc.ScalarType) == np.dtype(
            np.complex128
        ),
        "int32_petsc": np.dtype(PETSc.IntType) == np.dtype(np.int32),
        "serial_preflight_only": MPI.COMM_WORLD.size == 1,
    }
    if not all(checks.values()):
        raise RuntimeError(
            "inverse budget-exchange ABI gate failed: "
            + ", ".join(
                name for name, passed in checks.items() if not passed
            )
        )
    return {
        "checks": checks,
        "python_executable": str(executable),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "basix_version": basix.__version__,
        "petsc4py_version": petsc4py.__version__,
        "mpi4py_version": mpi4py.__version__,
        "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
        "petsc_int_type": np.dtype(PETSc.IntType).name,
        "mpi_world_size": MPI.COMM_WORLD.size,
    }


def build_preflight_record(
    *,
    source_identity: Mapping[str, Any],
    environment_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the lightweight evidence payload without writing it."""

    audit = audit_inverse_trace_interior_budget_exchange()
    return {
        **audit,
        "benchmark_id": (
            "task035b_inverse_trace_interior_budget_exchange_preflight"
        ),
        "source": dict(source_identity),
        "environment": dict(environment_identity),
        "execution_scope": {
            "serial": True,
            "lightweight": True,
            "basix_only_numerical_audit": True,
            "mesh_built": False,
            "form_compiled": False,
            "matrix_assembled": False,
            "mpi_pde_launched": False,
            "pde_run": False,
        },
        "record_semantics": (
            "controlled-negative structural preflight; pass means the "
            "fail-closed audit completed, not that a PDE candidate passed"
        ),
    }


def _write_json_exclusive(
    path: Path,
    record: Mapping[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _resolve_output(path: Path) -> Path:
    output = (path if path.is_absolute() else ROOT / path).resolve()
    try:
        output.relative_to(RECORDS.resolve())
    except ValueError as error:
        raise ValueError(
            "inverse budget-exchange evidence must remain in Case095 records"
        ) from error
    return output


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output = _resolve_output(args.output)
    if output.exists():
        raise FileExistsError(
            f"exclusive output already exists: {output}"
        )
    source = _verified_source_identity(
        ROOT,
        args.verified_clean_sha,
    )
    environment = _environment_identity(ROOT)
    record = build_preflight_record(
        source_identity=source,
        environment_identity=environment,
    )
    record["source"] = _close_source_identity(ROOT, source)
    _write_json_exclusive(output, record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
