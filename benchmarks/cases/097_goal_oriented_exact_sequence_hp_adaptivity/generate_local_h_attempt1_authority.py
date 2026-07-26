#!/usr/bin/env python3
"""Generate or compare Task035d true-local-h Attempt 1 authorities."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

import basix
import dolfinx
from mpi4py import MPI
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adaptivity.dyadic_hexa_broken_mesh import (  # noqa: E402
    build_broken_dyadic_hexa_carrier,
)
from src.adaptivity.dyadic_hexa_refinement import (  # noqa: E402
    DyadicHexKey,
    build_root_dyadic_hexa_forest,
    refine_balanced_dyadic_hexa_forest,
)
from src.adaptivity.hcurl_broken_trace_graph import (  # noqa: E402
    build_broken_hexa_trace_constraint_authority,
)
from src.adaptivity.hcurl_hanging_trace import (  # noqa: E402
    build_hanging_face_reference_pair,
    build_oriented_hanging_face_reference_catalog,
    random_hanging_static_condensation_audit,
)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_plain(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return _sha256(path)


def _tensor_boxes(
    nx: int,
    ny: int,
    nz: int,
) -> list[tuple[float, float, float, float, float, float]]:
    return [
        (
            float(i),
            float(j),
            float(k),
            float(i + 1),
            float(j + 1),
            float(k + 1),
        )
        for k in range(nz)
        for j in range(ny)
        for i in range(nx)
    ]


def _simple_fixture(comm: MPI.Intracomm):
    forest = build_root_dyadic_hexa_forest(
        _tensor_boxes(2, 1, 1),
        [1, 1],
        periodic_axes=(),
    )
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(0, 0, 0, 0, 0)],
    )
    return forest, build_broken_dyadic_hexa_carrier(forest, comm=comm)


def _periodic_fixture(comm: MPI.Intracomm):
    boxes = _tensor_boxes(3, 3, 1)
    forest = build_root_dyadic_hexa_forest(
        boxes,
        [1] * len(boxes),
        periodic_axes=("x", "y"),
    )
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(0, 0, 0, 0, 0)],
    )
    return forest, build_broken_dyadic_hexa_carrier(forest, comm=comm)


def generate_authority(
    *,
    comm: MPI.Intracomm,
    source_sha: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("source SHA must be 40 lowercase hexadecimal digits")
    oriented = {
        str(degree): dict(
            build_oriented_hanging_face_reference_catalog(degree)
        )
        for degree in (4, 5, 6)
    }
    canonical = {
        str(degree): {
            **dict(build_hanging_face_reference_pair(degree).audit),
            "static_schur": random_hanging_static_condensation_audit(
                build_hanging_face_reference_pair(degree),
                seed=350197 + degree,
            ),
        }
        for degree in (4, 5, 6)
    }
    simple_forest, simple_carrier = _simple_fixture(comm)
    simple_graphs = {
        str(degree): dict(
            build_broken_hexa_trace_constraint_authority(
                simple_forest,
                simple_carrier,
                degree=degree,
            ).audit
        )
        for degree in (4, 5, 6)
    }
    periodic_forest, periodic_carrier = _periodic_fixture(comm)
    periodic_graph = build_broken_hexa_trace_constraint_authority(
        periodic_forest,
        periodic_carrier,
        degree=4,
        phase_x=np.exp(0.2j),
        phase_y=np.exp(-0.3j),
    )
    stable_identity = {
        "oriented_catalog_sha256": {
            degree: row["oriented_child_catalog_sha256"]
            for degree, row in oriented.items()
        },
        "canonical_hcurl_restriction_sha256": {
            degree: row["hcurl_restriction_sha256"]
            for degree, row in canonical.items()
        },
        "simple_leaf_catalog_sha256": simple_forest.audit[
            "leaf_catalog_sha256"
        ],
        "simple_carrier_connectivity_sha256": simple_carrier.audit[
            "canonical_connectivity_sha256"
        ],
        "simple_physical_authority_sha256": {
            degree: row["physical_authority_sha256"]
            for degree, row in simple_graphs.items()
        },
        "periodic_leaf_catalog_sha256": periodic_forest.audit[
            "leaf_catalog_sha256"
        ],
        "periodic_carrier_connectivity_sha256": periodic_carrier.audit[
            "canonical_connectivity_sha256"
        ],
        "periodic_physical_authority_sha256": periodic_graph.audit[
            "physical_authority_sha256"
        ],
    }
    checks = {
        "oriented_p4_p5_p6": all(row["pass"] for row in oriented.values()),
        "canonical_p4_p5_p6": all(
            row["pass"] and row["static_schur"]["pass"]
            for row in canonical.values()
        ),
        "simple_carrier": simple_carrier.audit["pass"],
        "simple_actual_hanging_p4_p5_p6": all(
            row["pass"] for row in simple_graphs.values()
        ),
        "periodic_carrier": periodic_carrier.audit["pass"],
        "periodic_hanging_floquet_graph": periodic_graph.audit["pass"],
        "periodic_secondary_compatibility": (
            periodic_graph.audit["maximum_relation_residual"] <= 5.0e-11
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "case097.local-h-attempt1-authority.v1",
        "status": (
            "local_h_attempt1_component_authority_pass"
            if not failures
            else "local_h_attempt1_component_authority_fail"
        ),
        "pass": not failures,
        "source_sha": source_sha,
        "mpi_size": int(comm.size),
        "environment": {
            "dolfinx": dolfinx.__version__,
            "basix": basix.__version__,
            "scalar_type": str(np.dtype(np.complex128)),
        },
        "oriented_hanging_catalogs": oriented,
        "canonical_hanging_catalogs": canonical,
        "simple_forest": dict(simple_forest.audit),
        "simple_carrier": dict(simple_carrier.audit),
        "simple_actual_hanging_graphs": simple_graphs,
        "periodic_forest": dict(periodic_forest.audit),
        "periodic_carrier": dict(periodic_carrier.audit),
        "periodic_actual_hanging_floquet_graph": dict(
            periodic_graph.audit
        ),
        "stable_identity": stable_identity,
        "checks": checks,
        "failures": failures,
        "compiled_cell_tensor_binding_complete": False,
        "heavy_pde_started": False,
        "pde_accuracy_credit": False,
        "ordinary_default_changed": False,
    }


def compare_authorities(
    records: tuple[Path, ...],
) -> dict[str, Any]:
    if len(records) != 3:
        raise ValueError("comparison requires MPI1, MPI2, and MPI8 records")
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in records]
    mpi_sizes = {int(payload["mpi_size"]) for payload in payloads}
    source_shas = {str(payload["source_sha"]) for payload in payloads}
    identities = [payload["stable_identity"] for payload in payloads]
    checks = {
        "input_records_pass": all(payload["pass"] for payload in payloads),
        "mpi_sizes_are_1_2_8": mpi_sizes == {1, 2, 8},
        "same_source_sha": len(source_shas) == 1,
        "stable_physical_identity": all(
            identity == identities[0] for identity in identities[1:]
        ),
        "no_heavy_pde": all(
            payload["heavy_pde_started"] is False for payload in payloads
        ),
        "no_pde_accuracy_credit": all(
            payload["pde_accuracy_credit"] is False for payload in payloads
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "case097.local-h-attempt1-mpi-comparison.v1",
        "status": (
            "local_h_attempt1_mpi1_mpi2_mpi8_identity_pass"
            if not failures
            else "local_h_attempt1_mpi_identity_fail"
        ),
        "pass": not failures,
        "source_sha": next(iter(source_shas)) if len(source_shas) == 1 else None,
        "mpi_sizes": sorted(mpi_sizes),
        "input_records": [
            {
                "path": str(path),
                "sha256": _sha256(path),
            }
            for path in records
        ],
        "stable_identity": identities[0] if identities else None,
        "checks": checks,
        "failures": failures,
        "component_scope": (
            "dyadic forest + broken carrier + p4/p5/p6 orientation + "
            "physical hanging/Floquet flattened graph"
        ),
        "compiled_cell_tensor_binding_complete": False,
        "heavy_pde_started": False,
        "pde_accuracy_credit": False,
        "ordinary_default_changed": False,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha")
    parser.add_argument(
        "--compare-records",
        type=Path,
        nargs=3,
        metavar=("MPI1", "MPI2", "MPI8"),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    comm = MPI.COMM_WORLD
    if args.compare_records is not None:
        if comm.size != 1:
            raise RuntimeError("record comparison must run in serial")
        payload = compare_authorities(tuple(args.compare_records))
    else:
        if args.source_sha is None:
            raise ValueError("--source-sha is required for generation")
        payload = generate_authority(
            comm=comm,
            source_sha=str(args.source_sha),
        )
    if comm.rank == 0:
        digest = _write(args.output, payload)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "sha256": digest,
                    "status": payload["status"],
                    "pass": payload["pass"],
                },
                sort_keys=True,
            )
        )
    comm.Barrier()
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
