from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from mpi4py import MPI

from src.validation.task035_component_fixtures import run_component_fixture_suite


def _identity(record: Mapping[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(record))
    result.pop("mpi_size", None)
    result["b3"].pop("mpi_size", None)
    result["b4"].pop("mpi_size", None)
    return result


def compare_serial_mpi2(
    serial: Mapping[str, Any], mpi2: Mapping[str, Any]
) -> dict[str, Any]:
    failures = []
    if serial.get("mpi_size") != 1:
        failures.append("serial_mpi_size")
    if mpi2.get("mpi_size") != 2:
        failures.append("mpi2_mpi_size")
    if _identity(serial) != _identity(mpi2):
        failures.append("component_metrics")
    return {
        "schema_version": "task035.phase-c-component-mpi-identity.v1",
        "status": "serial_mpi2_identity_pass"
        if not failures
        else "serial_mpi2_identity_fail",
        "pass": not failures,
        "failures": failures,
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
        record = run_component_fixture_suite()
    _write(record, args.output)
    return 0 if record.get("pass", record["status"] == "B3_B4_pass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
