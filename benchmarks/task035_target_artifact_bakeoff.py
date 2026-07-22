from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from src.validation.task035_target_artifact_bakeoff import run_target_artifact_bakeoff


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provenance() -> dict[str, Any]:
    runner = Path(__file__).resolve()
    implementation = ROOT / "src/validation/task035_target_artifact_bakeoff.py"
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    return {
        "git_head_at_run": head,
        "python_executable": sys.executable,
        "qualified_activation": os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION"),
        "petsc_scalar_dtype": np.dtype(PETSc.ScalarType).name,
        "petsc_int_dtype": np.dtype(PETSc.IntType).name,
        "tracked_content_bindings": {
            str(runner.relative_to(ROOT)): _sha256(runner),
            str(implementation.relative_to(ROOT)): _sha256(implementation),
        },
    }


def _identity_values(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": record["status"],
        "phase_c_internal_gate": record["phase_c_internal_gate"],
        "target_artifact_screen_pass": record["target_artifact_screen_pass"],
        "production_estimator_selected": record["production_estimator_selected"],
        "points": record["points"],
        "actual_refinement_evidence": record["actual_refinement_evidence"],
        "artifact_bindings": record["artifact_bindings"],
        "convergence_record": record["convergence_record"],
    }


def compare_serial_mpi2(
    serial: Mapping[str, Any], mpi2: Mapping[str, Any]
) -> dict[str, Any]:
    failures = []
    if serial.get("mpi_size") != 1:
        failures.append("serial_mpi_size")
    if mpi2.get("mpi_size") != 2:
        failures.append("mpi2_mpi_size")
    left = _identity_values(serial)
    right = _identity_values(mpi2)
    if left != right:
        failures.append("deterministic_estimator_metrics")
    for record in (serial, mpi2):
        if not all(
            math.isfinite(float(row["R1_sampled_strong_residual_proxy"]["norm"]))
            for row in record["points"]
        ):
            failures.append("nonfinite_R1")
    return {
        "schema_version": "task035.target-artifact-mpi-identity.v1",
        "status": "serial_mpi2_identity_pass"
        if not failures
        else "serial_mpi2_identity_fail",
        "pass": not failures,
        "failures": failures,
        "comparison": "deterministic compact estimator metrics; cost and mpi metadata excluded",
    }


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(record: Mapping[str, Any], output: Path | None) -> None:
    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if MPI.COMM_WORLD.rank == 0:
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload, encoding="utf-8")
        print(payload, end="")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("SERIAL", "MPI2"))
    args = parser.parse_args(argv)
    if args.compare:
        record = compare_serial_mpi2(_read(args.compare[0]), _read(args.compare[1]))
    else:
        record = run_target_artifact_bakeoff()
        record["provenance"] = _provenance()
    _write(record, args.output)
    return 0 if record.get("pass", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
