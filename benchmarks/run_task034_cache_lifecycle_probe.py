"""Repeated small-case RSS/weak-owner probe for the Task034 Floquet cache."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import gc
import json
from pathlib import Path
import tempfile
import weakref

from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI

from src.common.config_3d import oblique_incidence_airbox_config
from src.constraints.floquet_3d_high_order import (
    build_high_order_constraint_data,
    clear_floquet_topology_cache,
    floquet_topology_cache_size,
)
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d


def _rss_bytes() -> int | None:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def run(case_count: int) -> dict:
    comm = MPI.COMM_WORLD
    records = []
    all_released = True
    all_phase_hits = True
    all_cleared = True
    for index in range(case_count):
        cfg = oblique_incidence_airbox_config(
            case_name=f"task034_cache_lifecycle_{index}",
            stage_case="floquet_airbox",
            geometry_kind="airbox",
            lambda0=13.5,
            period_x=10.0,
            period_y=10.0,
            z_min=0.0,
            z_max=10.0,
            use_floquet_xy=True,
            use_pml=False,
            incident_theta_deg=37.0,
            incident_phi_deg=23.0,
            polarization_kind="s",
            custom_polarization=None,
            nedelec_degree=3,
            visualization_degree=1,
            mesh_target_size=5.0,
            mesh_cell_type="hexahedron",
            floquet_constraint_mode="auto",
        )
        with tempfile.TemporaryDirectory(prefix="task034_cache_") as directory:
            mesh_data = build_airbox_mesh_3d(cfg, Path(directory))
            V = fem.functionspace(
                mesh_data.mesh,
                element(
                    "N1curl", mesh_data.mesh.basix_cell(), 3,
                    dtype=default_real_type,
                ),
            )
            first = build_high_order_constraint_data(V, mesh_data, cfg)
            second = build_high_order_constraint_data(
                V, mesh_data,
                replace(cfg, incident_theta_deg=19.0, incident_phi_deg=41.0),
            )
            phase_hit = bool(second.topology_cache_hit and first.topology is second.topology)
            mesh_ref = weakref.ref(mesh_data.mesh)
            space_ref = weakref.ref(V)
            del first, second, V, mesh_data
            clear_floquet_topology_cache()
            gc.collect()
            released = mesh_ref() is None and space_ref() is None
            cache_empty = floquet_topology_cache_size() == 0
            all_phase_hits &= phase_hit
            all_released &= released
            all_cleared &= cache_empty
            records.append({
                "case_index": index,
                "phase_only_cache_hit": phase_hit,
                "owners_released_after_clear": released,
                "cache_empty": cache_empty,
                "rss_bytes": _rss_bytes(),
            })
    local_rss = [row["rss_bytes"] for row in records if row["rss_bytes"] is not None]
    local_growth = 0 if len(local_rss) < 3 else max(local_rss[2:]) - min(local_rss[2:])
    max_growth = comm.allreduce(local_growth, op=MPI.MAX)
    rank_records = comm.gather(records, root=0)
    checks = {
        "phase_only_hits_all_cases": bool(comm.allreduce(all_phase_hits, op=MPI.LAND)),
        "weak_owners_released_all_cases": bool(comm.allreduce(all_released, op=MPI.LAND)),
        "cache_empty_after_every_case": bool(comm.allreduce(all_cleared, op=MPI.LAND)),
        "post_warmup_rss_growth_le_64_mib": max_growth <= 64 * 1024**2,
        "mpi_rank_count_consistent": comm.allreduce(1, op=MPI.SUM) == comm.size,
    }
    return {
        "schema_version": "task034.floquet-cache-lifecycle.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "cache_lifecycle_pass" if all(checks.values()) else "cache_lifecycle_fail",
        "formal_pass": all(checks.values()),
        "mpi_size": comm.size,
        "case_count": case_count,
        "max_post_warmup_rss_growth_bytes": max_growth,
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "rank_records": rank_records if comm.rank == 0 else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-count", type=int, default=12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    record = run(args.case_count)
    if MPI.COMM_WORLD.rank == 0:
        rendered = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        print(json.dumps({"status": record["status"], "failures": record["failures"]}))
    passed = MPI.COMM_WORLD.bcast(record["formal_pass"] if MPI.COMM_WORLD.rank == 0 else None, root=0)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
