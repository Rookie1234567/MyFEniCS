from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Any, Mapping

import basix
import dolfinx
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.task034_adaptive_mesh import (
    Task034Stage4Geometry,
    build_task034_conforming_graded_plan,
    build_task034_graded_local_mesh_pair,
)
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.solvers.common_3d_solve import _create_nedelec_space


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT
    / "benchmarks"
    / "artifacts"
    / "cases"
    / "092"
    / "adaptive"
    / "p2_h5_mechanism_mpi8.json"
)


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ("git", *arguments), cwd=ROOT, text=True, stderr=subprocess.STDOUT
    ).strip()


def _source_identity() -> dict[str, Any]:
    status = _git("status", "--porcelain", "--untracked-files=all")
    return {
        "commit_sha": _git("rev-parse", "HEAD").lower(),
        "tracked_and_nonignored_untracked_clean": status == "",
        "status_porcelain": status,
    }


def _space_size(function_space) -> int:
    return int(
        function_space.dofmap.index_map.size_global
        * function_space.dofmap.index_map_bs
    )


def _rank_environment() -> dict[str, Any]:
    return {
        "rank": MPI.COMM_WORLD.rank,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "mpi_library": MPI.Get_library_version().strip(),
        "petsc_version": ".".join(str(value) for value in PETSc.Sys.getVersion()),
        "petsc_scalar_type": str(PETSc.ScalarType),
        "petsc_int_type": str(PETSc.IntType),
        "dolfinx_version": dolfinx.__version__,
        "basix_version": basix.__version__,
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
        "openblas_num_threads": os.environ.get("OPENBLAS_NUM_THREADS"),
        "mkl_num_threads": os.environ.get("MKL_NUM_THREADS"),
    }


def _floquet_record(data) -> dict[str, Any]:
    return {
        "constraint_mode_resolved": data.constraint_mode_resolved,
        "num_constraints": int(data.num_constraints),
        "num_x_constraints": int(data.num_x_constraints),
        "num_y_constraints": int(data.num_y_constraints),
        "num_corner_constraints": int(data.num_corner_constraints),
        "raw_map_nnz": int(data.raw_map_nnz),
        "max_masters_per_slave": int(data.max_masters_per_slave),
        "max_face_pairing_coordinate_error": float(
            data.max_face_pairing_coordinate_error
        ),
        "edge_corner_phase_mismatch": float(data.edge_corner_phase_mismatch),
        "max_edge_midpoint_pairing_error": float(
            data.max_edge_midpoint_pairing_error
        ),
        "max_face_midpoint_pairing_error": float(
            data.max_face_midpoint_pairing_error
        ),
        "max_face_transform_fit_residual": float(
            data.max_face_transform_fit_residual
        ),
        "used_full_boundary_gather": bool(data.used_full_boundary_gather),
        "created_dense_boundary_square": bool(data.created_dense_boundary_square),
        "estimated_constraint_memory_mb": float(
            data.estimated_constraint_memory_mb
        ),
        "communication_bytes_sent_current": int(
            data.communication_bytes_sent_current
        ),
        "communication_bytes_received_current": int(
            data.communication_bytes_received_current
        ),
    }


def evaluate_mechanism_record(record: Mapping[str, Any]) -> dict[str, Any]:
    source_before = record.get("source_before", {})
    source_after = record.get("source_after", {})
    plan = record.get("plan", {})
    local_meshes = record.get("local_meshes", {})
    bottom = local_meshes.get("bottom", {}) if isinstance(local_meshes, Mapping) else {}
    top = local_meshes.get("top", {}) if isinstance(local_meshes, Mapping) else {}
    rank_environments = record.get("rank_environments", [])
    rank_environments = rank_environments if isinstance(rank_environments, list) else []
    runtime = record.get("runtime", {})
    cross_section = record.get("cross_section", {})

    def rank_identity(environment: Mapping[str, Any]) -> tuple[Any, ...]:
        return tuple(
            environment.get(key)
            for key in (
                "python_executable",
                "python_version",
                "mpi_library",
                "petsc_version",
                "petsc_scalar_type",
                "petsc_int_type",
                "dolfinx_version",
                "basix_version",
                "omp_num_threads",
                "openblas_num_threads",
                "mkl_num_threads",
            )
        )

    checks = {
        "schema_identity": record.get("schema_version")
        == "task034.adaptive-mechanism.v1",
        "frozen_case_identity": bool(
            record.get("case")
            == {
                "degree": 2,
                "reference_h_nm": 5.0,
                "bottom_interface_nm": 10.0,
                "top_interface_nm": 110.0,
                "profile": "mechanism",
                "polarization_kind": "s",
            }
        ),
        "clean_source_before_after": bool(
            source_before.get("tracked_and_nonignored_untracked_clean") is True
            and source_after.get("tracked_and_nonignored_untracked_clean") is True
            and source_before.get("commit_sha") == source_after.get("commit_sha")
            and source_before.get("commit_sha") == record.get("verified_clean_sha")
        ),
        "mpi8_without_oversubscription": bool(
            runtime.get("mpi_size") == 8
            and runtime.get("available_physical_cores", 0) >= 8
        ),
        "rank_environment_identity": bool(
            len(rank_environments) == runtime.get("mpi_size")
            and len({rank_identity(item) for item in rank_environments}) == 1
        ),
        "complex_petsc_scalar": bool(
            rank_environments
            and "complex" in str(rank_environments[0].get("petsc_scalar_type"))
        ),
        "deterministic_plan_hash_all_ranks": bool(
            len(record.get("plan_hashes_all_ranks", [])) == runtime.get("mpi_size")
            and len(set(record.get("plan_hashes_all_ranks", []))) == 1
            and record.get("plan_hashes_all_ranks", [None])[0]
            == plan.get("plan_hash")
        ),
        "conforming_hexa_contract": bool(
            plan.get("material_planes_exact") is True
            and plan.get("matching_planes_exact") is True
            and plan.get("quality", {}).get("hanging_nodes_present") is False
            and plan.get("quality", {}).get("positive_jacobian_proxy") is True
            and plan.get("quality", {}).get("axis_width_ratio", 1.0e30) <= 8.0
        ),
        "periodic_trace_contract": bool(
            plan.get("periodic_pairing", {}).get("x_trace_synchronized") is True
            and plan.get("periodic_pairing", {}).get("y_trace_synchronized") is True
            and plan.get("periodic_pairing", {}).get(
                "periodic_mate_refinement_synchronized"
            )
            is True
        ),
        "bottom_top_trace_identity": bool(
            bottom.get("mesh_cells_xy") == top.get("mesh_cells_xy")
            and bottom.get("global_interface_facet_count")
            == top.get("global_interface_facet_count")
            == bottom.get("expected_interface_facet_count")
            and bottom.get("interface_z_nm") == 10.0
            and top.get("interface_z_nm") == 110.0
        ),
        "matching_cross_section_identity": bool(
            cross_section.get("mesh_cells_xy") == bottom.get("mesh_cells_xy")
            and cross_section.get("mixed_global_dofs", 0) > 0
        ),
        "floquet_constraints_qualified": bool(
            all(
                item.get("num_constraints", 0) > 0
                and item.get("constraint_mode_resolved") == "topological_trace_p2"
                and item.get("used_full_boundary_gather") is False
                and item.get("created_dense_boundary_square") is False
                and item.get("max_face_pairing_coordinate_error", 1.0) <= 1.0e-10
                and item.get("edge_corner_phase_mismatch", 1.0) <= 1.0e-10
                for item in (bottom.get("floquet", {}), top.get("floquet", {}))
            )
        ),
        "ordinary_default_unchanged": plan.get("ordinary_uniform_default_changed")
        is False,
        "no_pde_solve_claim": record.get("claims", {}).get("pde_solved") is False,
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task034 p2/h5 conforming graded-h mechanism qualification"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--available-physical-cores", type=int, required=True)
    parser.add_argument("--check", type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.check is not None:
        record = json.loads(args.check.read_text(encoding="utf-8"))
        decision = evaluate_mechanism_record(record)
        print(json.dumps(decision, ensure_ascii=False, indent=2))
        raise SystemExit(0 if decision["pass"] else 1)

    comm = MPI.COMM_WORLD
    started = time.perf_counter()
    source_before = _source_identity()
    if (
        source_before["commit_sha"] != args.verified_clean_sha.lower()
        or source_before["tracked_and_nonignored_untracked_clean"] is not True
    ):
        raise SystemExit("Task034 mechanism requires the requested clean source SHA.")
    if args.available_physical_cores < comm.size:
        raise SystemExit("Task034 mechanism forbids MPI oversubscription.")

    cfg = target_stage4_config(degree=2, h_nm=5.0)
    geometry = Task034Stage4Geometry.from_config(cfg)
    plan = build_task034_conforming_graded_plan(
        reference_h_nm=5.0,
        geometry=geometry,
        profile="mechanism",
        coarse_factor=2.0,
        comm_size=comm.size,
    )
    bottom, top = build_task034_graded_local_mesh_pair(cfg, plan, comm=comm)
    local_records: dict[str, dict[str, Any]] = {}
    for local in (bottom, top):
        space = _create_nedelec_space(local.mesh, cfg)
        floquet = build_double_floquet_mpc(space, local.mesh_data, cfg)
        local_records[local.side] = {
            "mesh_cells_xyz": list(local.mesh_cells),
            "mesh_cells_xy": list(local.mesh_cells[:2]),
            "global_interface_facet_count": local.global_interface_facet_count,
            "expected_interface_facet_count": local.mesh_cells[0]
            * local.mesh_cells[1],
            "interface_z_nm": local.interface_z_nm,
            "external_z_nm": local.external_z_nm,
            "nedelec_global_dofs": _space_size(space),
            "floquet": _floquet_record(floquet),
        }

    cross_section = build_matching_cross_section(
        cfg,
        "stage4_xy",
        x_values=plan.x_values,
        y_values=plan.y_values,
        comm=comm,
    )
    spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
    rank_environments = comm.gather(_rank_environment(), root=0)
    plan_hashes = comm.gather(plan.plan_hash, root=0)
    source_after = _source_identity()
    record = None
    if comm.rank == 0:
        record = {
            "schema_version": "task034.adaptive-mechanism.v1",
            "record_type": "task034_p2_h5_conforming_graded_mechanism",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "verified_clean_sha": args.verified_clean_sha.lower(),
            "source_before": source_before,
            "source_after": source_after,
            "case": {
                "degree": 2,
                "reference_h_nm": 5.0,
                "bottom_interface_nm": 10.0,
                "top_interface_nm": 110.0,
                "profile": "mechanism",
                "polarization_kind": "s",
            },
            "runtime": {
                "mpi_size": comm.size,
                "available_physical_cores": args.available_physical_cores,
                "wall_seconds": time.perf_counter() - started,
            },
            "rank_environments": rank_environments,
            "plan_hashes_all_ranks": plan_hashes,
            "plan": plan.to_record(),
            "local_meshes": local_records,
            "cross_section": {
                "mesh_cells_xy": list(cross_section.mesh_cells),
                "mixed_global_dofs": _space_size(spaces.mixed),
                "transverse_global_dofs": _space_size(spaces.transverse),
                "longitudinal_global_dofs": _space_size(spaces.longitudinal),
            },
            "claims": {
                "mechanism_qualified": False,
                "pde_solved": False,
                "equal_accuracy_compression_proven": False,
                "genuine_adaptive_loop_proven": False,
            },
        }
        decision = evaluate_mechanism_record(record)
        record["qualification"] = decision
        record["claims"]["mechanism_qualified"] = decision["pass"]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(decision, ensure_ascii=False, indent=2), flush=True)
    passed = comm.bcast(None if record is None else record["qualification"]["pass"], root=0)
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
