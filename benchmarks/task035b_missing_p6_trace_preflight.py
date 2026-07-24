"""Write the lightweight Task035b missing-p6-trace preflight evidence.

This generator performs only Basix/reference-cell algebra.  It does not build
a mesh, compile a form, assemble a global matrix, launch MPI, or run a PDE.
The output is deliberately exclusive-create so historical evidence cannot be
overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence

import basix
import dolfinx
from mpi4py import MPI
import mpi4py
import numpy as np
from petsc4py import PETSc
import petsc4py
import scipy

from src.adaptivity.missing_p6_trace_sensitivity import (
    build_missing_p6_trace_complement,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = (
    "codex/20260723-task35b-high-order-local-hp-resource-envelope"
)
DEFAULT_OUTPUT = Path(
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
    "records/missing_p6_trace_complement_preflight_v1.json"
)
SOURCE_FILES = (
    "benchmarks/task035b_missing_p6_trace_preflight.py",
    "src/adaptivity/missing_p6_trace_sensitivity.py",
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


def _verified_source_identity(
    repo_root: Path,
    verified_clean_sha: str,
) -> dict[str, Any]:
    verified = str(verified_clean_sha).lower()
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    checks = {
        "full_verified_sha": (
            len(verified) == 40
            and all(
                character in "0123456789abcdef"
                for character in verified
            )
        ),
        "head_matches_verified_sha": head == verified,
        "expected_branch": branch == EXPECTED_BRANCH,
        "tracked_and_untracked_worktree_clean": status == "",
    }
    if not all(checks.values()):
        raise SystemExit(
            "missing-p6-trace source gate failed: "
            + ", ".join(
                name for name, passed in checks.items() if not passed
            )
        )
    return {
        "commit_sha": head,
        "verified_clean_sha": verified,
        "branch": branch,
        "tracked_source_dirty": False,
        "stable_and_clean_before": True,
        "cleanliness_command": (
            "git status --short --untracked-files=all"
        ),
        "checks": checks,
    }


def _environment_identity(repo_root: Path) -> dict[str, Any]:
    executable = Path(sys.executable).resolve()
    expected_python = (repo_root / ".venv/bin/python").resolve()
    checks = {
        "qualified_activation_marker": (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
        ),
        "repo_virtualenv_python": executable == expected_python,
        "working_directory_is_repo_root": (
            Path.cwd().resolve() == repo_root
        ),
        "linux_runtime": sys.platform.startswith("linux"),
        "complex128_petsc": np.dtype(PETSc.ScalarType) == np.dtype(
            np.complex128
        ),
        "int32_petsc": np.dtype(PETSc.IntType) == np.dtype(np.int32),
        "serial_preflight_only": MPI.COMM_WORLD.size == 1,
    }
    if not all(checks.values()):
        raise RuntimeError(
            "missing-p6-trace environment gate failed: "
            + ", ".join(
                name for name, passed in checks.items() if not passed
            )
        )
    return {
        "schema_version": (
            "task035b.missing-p6-trace-environment.v1"
        ),
        "pass": True,
        "checks": checks,
        "python_executable": str(executable),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "uname": list(platform.uname()),
        "git_executable": shutil.which("git"),
        "mpiexec_executable": shutil.which("mpiexec"),
        "basix_version": basix.__version__,
        "dolfinx_version": dolfinx.__version__,
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "petsc4py_version": petsc4py.__version__,
        "mpi4py_version": mpi4py.__version__,
        "petsc_version": list(PETSc.Sys.getVersion()),
        "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
        "petsc_int_type": np.dtype(PETSc.IntType).name,
        "mpi_world_size": MPI.COMM_WORLD.size,
        "mpi_library_version": MPI.Get_library_version(),
        "qualified_activation_marker": (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION")
        ),
    }


def build_missing_p6_trace_preflight_record(
    repo_root: Path,
    *,
    source: Mapping[str, Any],
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    """Build complete structural evidence without starting a PDE."""

    complement = build_missing_p6_trace_complement()
    audit = dict(complement.audit)
    edge_missing = int(
        sum(audit["missing_edge_modes_per_entity"])
    )
    face_missing = int(
        sum(audit["missing_face_modes_per_entity"])
    )
    missing_total = edge_missing + face_missing
    source_checks = source.get("checks") or {}
    source_identity_pass = bool(
        source.get("branch") == EXPECTED_BRANCH
        and source.get("commit_sha") == source.get("verified_clean_sha")
        and isinstance(source.get("commit_sha"), str)
        and len(source["commit_sha"]) == 40
        and all(
            character in "0123456789abcdef"
            for character in source["commit_sha"].lower()
        )
        and source.get("tracked_source_dirty") is False
        and source.get("stable_and_clean_before") is True
        and bool(source_checks)
        and all(value is True for value in source_checks.values())
    )
    qualification_checks = {
        "clean_source_identity_hash_bound": source_identity_pass,
        "qualified_environment": environment.get("pass") is True,
        "complete_complement_audit_pass": audit["pass"] is True,
        "retained_dimension_is_750": (
            complement.retained_dimension == 750
        ),
        "enriched_dimension_is_882": (
            complement.enriched_dimension == 882
        ),
        "missing_trace_mode_count_is_132": missing_total == 132,
        "missing_modes_are_edge_face_trace_only": (
            edge_missing == 12 and face_missing == 120
        ),
        "candidate_matrix_not_constructed": (
            audit["candidate_matrix_constructed"] is False
        ),
        "inactive_p6_rows_not_retained": (
            audit[
                "inactive_p6_rows_retained_in_candidate_matrix"
            ]
            is False
        ),
        "actual_dwr_not_claimed": (
            audit["actual_dwr_indicator"] is False
        ),
        "lane_b_selection_not_authorized": (
            audit["lane_b_formal_selection_authorized"] is False
        ),
        "pde_not_run": True,
    }
    passed = all(qualification_checks.values())
    return {
        "schema_version": (
            "task035b.missing-p6-trace-complement-preflight.v1"
        ),
        "benchmark_id": (
            "task035b_missing_p6_trace_complement_preflight"
        ),
        "status": (
            "missing_p6_trace_complement_preflight_pass"
            if passed
            else "missing_p6_trace_complement_preflight_fail"
        ),
        "pass": passed,
        "classification": "lightweight_structural_evidence",
        "source": dict(source),
        "source_file_sha256": {
            path: _sha256(repo_root / path) for path in SOURCE_FILES
        },
        "environment": dict(environment),
        "scope": {
            "geometry": "Task034 fixed rectangular block grating",
            "cell_type": "hexahedron",
            "trace_degree": 5,
            "interior_degree": 6,
            "enriched_trace_degree": 6,
            "ordinary_default_changed": False,
            "scientific_gate_relaxed": False,
        },
        "pde": {
            "status": "not_run",
            "heavy_case_started": False,
            "mesh_built": False,
            "form_compiled": False,
            "global_matrix_assembled": False,
            "factorization_started": False,
            "solver_started": False,
            "solver_failure": False,
        },
        "missing_trace_mode_inventory": {
            "reference_cell_missing_trace_modes": missing_total,
            "missing_edge_modes": edge_missing,
            "missing_face_modes": face_missing,
            "missing_cell_interior_modes": 0,
            "edge_count": len(
                audit["missing_edge_modes_per_entity"]
            ),
            "face_count": len(
                audit["missing_face_modes_per_entity"]
            ),
            "missing_modes_per_edge": list(
                audit["missing_edge_modes_per_entity"]
            ),
            "missing_modes_per_face": list(
                audit["missing_face_modes_per_entity"]
            ),
        },
        "complement_audit": audit,
        "diagnostic_semantics": {
            "candidate_matrix_constructed": False,
            "inactive_p6_rows_retained_in_candidate_matrix": False,
            "actual_missing_trace_residual_computed": False,
            "actual_missing_trace_adjoint_residual_computed": False,
            "actual_dwr_indicator": False,
            "lane_b_formal_selection_authorized": False,
            "reason": (
                "This record qualifies only the reference-cell p5/p6 "
                "entity complement. No target operator, residual, adjoint "
                "correction, or selected trace candidate is run."
            ),
        },
        "qualification": {
            "pass": passed,
            "checks": qualification_checks,
        },
    }


def _write_record_exclusive(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write clean-SHA, qualified-environment evidence for the "
            "Task035b p5/p6 missing-trace complement without a PDE."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = args.repo_root.resolve()
    source = _verified_source_identity(
        repo_root,
        args.verified_clean_sha,
    )
    output = (
        args.output
        if args.output.is_absolute()
        else repo_root / args.output
    ).resolve()
    if not output.is_relative_to(repo_root):
        raise SystemExit(
            "missing-p6-trace output must remain inside the repository"
        )
    if output.exists():
        raise FileExistsError(
            f"refusing to overwrite existing evidence: {output}"
        )
    environment = _environment_identity(repo_root)
    record = build_missing_p6_trace_preflight_record(
        repo_root,
        source=source,
        environment=environment,
    )
    _write_record_exclusive(output, record)
    return 0 if record["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
