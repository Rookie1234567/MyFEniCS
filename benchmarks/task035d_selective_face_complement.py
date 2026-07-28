"""MPI identity runner for the Task035d selective p6-face preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Sequence

from mpi4py import MPI

from src.adaptivity.selective_face_complement import (
    build_selective_p6_face_reference_catalog,
)


_SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Qualify the non-hanging whole-face p5-to-p6 exact-sequence "
            "component without launching a PDE."
        )
    )
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-catalog-sha256")
    return parser.parse_args(argv)


def _encoded(payload: dict) -> bytes:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if _SOURCE_SHA.fullmatch(args.source_sha) is None:
        raise ValueError("source SHA must be a lowercase full Git SHA")
    catalog = build_selective_p6_face_reference_catalog()
    local_sha = str(catalog["catalog_sha256"])
    packets = MPI.COMM_WORLD.allgather(local_sha)
    mpi_identity = len(set(packets)) == 1
    expected_identity = (
        args.expected_catalog_sha256 is None
        or local_sha == args.expected_catalog_sha256
    )
    passed = bool(
        catalog["pass"] is True
        and mpi_identity
        and expected_identity
    )
    payload = {
        "schema_version": (
            "task035d.selective-p6-face-component-authority.v1"
        ),
        "status": (
            "selective_p6_face_component_authority_pass"
            if passed
            else "selective_p6_face_component_authority_fail"
        ),
        "pass": passed,
        "source_sha": args.source_sha,
        "mpi_size": int(MPI.COMM_WORLD.size),
        "catalog": catalog,
        "mpi_catalog_sha256_by_rank": packets,
        "mpi_partition_independent": mpi_identity,
        "expected_catalog_sha256": args.expected_catalog_sha256,
        "expected_catalog_identity_pass": expected_identity,
        "scope": {
            "non_hanging_whole_face_only": True,
            "periodic_orbit_closure_still_required": True,
            "dtn_port_complement_still_required": True,
            "heavy_pde_started": False,
            "heavy_pde_authorized": False,
        },
        "production_qualified": False,
        "ordinary_default_changed": False,
    }
    data = _encoded(payload)
    payload_sha = hashlib.sha256(data).hexdigest()
    if MPI.COMM_WORLD.rank == 0:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(data)
        print(
            json.dumps(
                {
                    "status": payload["status"],
                    "pass": passed,
                    "output": str(args.output),
                    "sha256": payload_sha,
                    "catalog_sha256": local_sha,
                },
                sort_keys=True,
            )
        )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
