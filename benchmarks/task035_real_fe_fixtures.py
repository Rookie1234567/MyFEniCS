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

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.validation.task035_real_fe_fixtures import run_real_fe_fixture_suite


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provenance() -> dict[str, Any]:
    validation_path = ROOT / "src/validation/task035_real_fe_fixtures.py"
    runner_path = Path(__file__).resolve()
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return {
        "git_head_at_run": completed.stdout.strip(),
        "python_executable": sys.executable,
        "qualified_activation": os.environ.get(
            "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
        ),
        "petsc_scalar_dtype": np.dtype(PETSc.ScalarType).name,
        "petsc_int_dtype": np.dtype(PETSc.IntType).name,
        "tracked_content_bindings": {
            "benchmarks/task035_real_fe_fixtures.py": _sha256(runner_path),
            "src/validation/task035_real_fe_fixtures.py": _sha256(
                validation_path
            ),
        },
    }


def _identity_scalars(record: Mapping[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for fixture_name in ("b1", "b2"):
        fixture = record[fixture_name]
        for index, point in enumerate(fixture["points"]):
            for name, value in point.items():
                if isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)):
                    result[f"{fixture_name}.points[{index}].{name}"] = float(value)
    return result


def compare_serial_mpi2(
    serial: Mapping[str, Any], mpi2: Mapping[str, Any]
) -> dict[str, Any]:
    failures: list[str] = []
    if serial.get("mpi_size") != 1:
        failures.append("serial_record_mpi_size")
    if mpi2.get("mpi_size") != 2:
        failures.append("mpi2_record_mpi_size")
    if serial.get("status") != "real_fe_fixture_minimum_pass":
        failures.append("serial_fixture_gate")
    if mpi2.get("status") != "real_fe_fixture_minimum_pass":
        failures.append("mpi2_fixture_gate")
    serial_values = _identity_scalars(serial)
    mpi2_values = _identity_scalars(mpi2)
    if set(serial_values) != set(mpi2_values):
        failures.append("metric_key_set")
    differences: dict[str, dict[str, float]] = {}
    for name in sorted(set(serial_values) & set(mpi2_values)):
        left = serial_values[name]
        right = mpi2_values[name]
        absolute = abs(left - right)
        tolerance = 5.0e-11 * max(1.0, abs(left), abs(right))
        if not math.isfinite(left) or not math.isfinite(right) or absolute > tolerance:
            failures.append(name)
            differences[name] = {
                "serial": left,
                "mpi2": right,
                "absolute_difference": absolute,
                "tolerance": tolerance,
            }
    return {
        "schema_version": "task035.real-fe-mpi-identity.v1",
        "status": "serial_mpi2_identity_pass" if not failures else "serial_mpi2_identity_fail",
        "pass": not failures,
        "failures": failures,
        "differences": differences,
        "comparison": "scalar fixture metrics only; no field/vector gather",
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_or_print(record: Mapping[str, Any], output: Path | None) -> None:
    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if MPI.COMM_WORLD.rank == 0:
        if output is not None:
            output = output.resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload, encoding="utf-8")
        print(payload, end="")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Task035 low-cost real Nedelec/H(curl) B1/B2 fixtures."
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("SERIAL", "MPI2"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.compare:
        if MPI.COMM_WORLD.size != 1:
            raise RuntimeError("Record comparison must run in serial.")
        record = compare_serial_mpi2(
            _read_json(args.compare[0]), _read_json(args.compare[1])
        )
        _write_or_print(record, args.output)
        return 0 if record["pass"] else 2
    record = run_real_fe_fixture_suite()
    record["provenance"] = _provenance()
    _write_or_print(record, args.output)
    return 0 if record["status"] == "real_fe_fixture_minimum_pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
