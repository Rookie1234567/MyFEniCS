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

from src.validation.task035_component_fixtures import run_component_fixture_suite
from src.validation.task035_mesh_backend_bakeoff import run_mesh_backend_bakeoff
from src.validation.task035_target_artifact_bakeoff import run_target_artifact_bakeoff


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATIONS = (
    "benchmarks/task035_phase_cd.py",
    "src/validation/task035_component_fixtures.py",
    "src/validation/task035_mesh_backend_bakeoff.py",
    "src/validation/task035_target_artifact_bakeoff.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provenance() -> dict[str, Any]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    return {
        "git_head_at_run": head,
        "tracked_and_nonignored_untracked_clean_at_start": not bool(status.strip()),
        "status_porcelain_at_start": status,
        "python_executable": sys.executable,
        "qualified_activation": os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION"),
        "petsc_scalar_dtype": np.dtype(PETSc.ScalarType).name,
        "petsc_int_dtype": np.dtype(PETSc.IntType).name,
        "tracked_content_bindings": {
            path: _sha256(ROOT / path) for path in IMPLEMENTATIONS
        },
    }


def run_phase_cd_suite() -> dict[str, Any]:
    provenance = _provenance()
    phase_c = run_target_artifact_bakeoff()
    components = run_component_fixture_suite()
    phase_c["B3"] = components["b3"]["status"]
    phase_c["B4"] = components["b4"]["status"]
    phase_d = run_mesh_backend_bakeoff()
    complete = (
        phase_c["phase_c_internal_gate"] == "complete_controlled_negative"
        and components["status"] == "B3_B4_pass"
        and phase_d["phase_d_internal_gate"] == "complete"
    )
    return {
        "schema_version": "task035.phase-cd-closeout.v1",
        "status": "phase_cd_complete_controlled_negative"
        if complete
        else "phase_cd_fail",
        "canonical": False,
        "production_estimator_selected": False,
        "production_backend_selected": False,
        "ordinary_default_changed": False,
        "phase_e_unlocked": False,
        "mpi_size": MPI.COMM_WORLD.size,
        "phase_c": phase_c,
        "B3_B4": components,
        "phase_d": phase_d,
        "provenance": provenance,
    }


def _compare(left: Any, right: Any, path: str, failures: list[str]) -> None:
    ignored = {
        "mpi_size",
        "estimator_cost",
        "provenance",
    }
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        keys = (set(left) | set(right)) - ignored
        for key in sorted(keys):
            if key not in left or key not in right:
                failures.append(f"{path}.{key}:missing")
            else:
                _compare(left[key], right[key], f"{path}.{key}", failures)
        return
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            failures.append(f"{path}:length")
            return
        for index, (a, b) in enumerate(zip(left, right)):
            _compare(a, b, f"{path}[{index}]", failures)
        return
    if isinstance(left, bool) or isinstance(right, bool):
        if left != right:
            failures.append(path)
        return
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        a = float(left)
        b = float(right)
        tolerance = 5.0e-10 * max(1.0, abs(a), abs(b))
        if not math.isfinite(a) or not math.isfinite(b) or abs(a - b) > tolerance:
            failures.append(path)
        return
    if left != right:
        failures.append(path)


def compare_serial_mpi2(
    serial: Mapping[str, Any], mpi2: Mapping[str, Any]
) -> dict[str, Any]:
    failures: list[str] = []
    if serial.get("mpi_size") != 1:
        failures.append("serial.mpi_size")
    if mpi2.get("mpi_size") != 2:
        failures.append("mpi2.mpi_size")
    _compare(serial, mpi2, "record", failures)
    return {
        "schema_version": "task035.phase-cd-mpi-identity.v1",
        "status": "serial_mpi2_identity_pass"
        if not failures
        else "serial_mpi2_identity_fail",
        "pass": not failures,
        "failures": failures,
        "comparison": "compact scalar/metadata identity; wall/RSS/provenance/mpi_size excluded",
    }


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
    parser.add_argument("--compare", nargs=2, type=Path)
    args = parser.parse_args(argv)
    if args.compare:
        serial = json.loads(args.compare[0].read_text(encoding="utf-8"))
        mpi2 = json.loads(args.compare[1].read_text(encoding="utf-8"))
        record = compare_serial_mpi2(serial, mpi2)
    else:
        record = run_phase_cd_suite()
    _write(record, args.output)
    passed = record.get(
        "pass", record.get("status") == "phase_cd_complete_controlled_negative"
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
