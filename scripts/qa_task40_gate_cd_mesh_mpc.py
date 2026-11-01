#!/usr/bin/env python3
"""Bounded live mesh/material/P6-Floquet QA for the staged gate_cd profile.

This command deliberately stops before variational-form compilation, global
matrix construction, factorization, or solving.  It writes only a compact JSON
receipt and the mesh builder's empty working directory under the supplied QA
directory; visualization exports are not called.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INPUT = ROOT / "input/task40_gate_cd/gate_cd_0p7_mapped_p6_staged.dat"
HOST_AVAILABLE_FLOOR_BYTES = 64 * 1024**3
EXPECTED_PROFILE = "task40_gate_cd_0p7_mapped_p6_direct_v1"
MPC_PAIRING_COORDINATE_TOLERANCE = 1.0e-10
MPC_FACE_TRANSFORM_FIT_TOLERANCE = 1.0e-8
_ACTIVE_PAYLOAD: dict[str, Any] | None = None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value: Any) -> Any:
    from collections.abc import Mapping

    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (complex, np.complexfloating)):
        number = complex(value)
        return [float(number.real), float(number.imag)]
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, np.ndarray):
        return {
            "shape": [int(item) for item in value.shape],
            "dtype": str(value.dtype),
            "sha256": hashlib.sha256(
                np.ascontiguousarray(value).view(np.uint8).tobytes()
            ).hexdigest(),
        }
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"cannot serialize QA fact of type {type(value).__name__}")


def _read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
        key, raw = line.split(":", 1)
        if key not in {"MemAvailable", "SwapTotal", "SwapFree"}:
            continue
        values[key] = int(raw.strip().split()[0]) * 1024
    return values


def _proc_status_kb(key: str) -> int | None:
    for line in Path("/proc/self/status").read_text(encoding="ascii").splitlines():
        if line.startswith(f"{key}:"):
            return int(line.split()[1]) * 1024
    return None


def _proc_start_ticks(pid: int) -> int:
    raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    fields_after_comm = raw.rsplit(")", 1)[1].split()
    # The tail begins at proc-stat field 3 (state); starttime is field 22.
    return int(fields_after_comm[19])


def _numa_maps_summary() -> dict[str, int]:
    counts = {
        "interleave_0_1_mappings": 0,
        "default_mappings": 0,
        "local_mappings": 0,
        "other_policy_mappings": 0,
        "unclassified_policy_mappings": 0,
    }
    for line in Path("/proc/self/numa_maps").read_text(encoding="ascii").splitlines():
        fields = line.split()
        if len(fields) < 2:
            counts["unclassified_policy_mappings"] += 1
            continue
        policy = fields[1]
        if policy == "interleave:0-1":
            counts["interleave_0_1_mappings"] += 1
        elif policy == "default":
            counts["default_mappings"] += 1
        elif policy == "local":
            counts["local_mappings"] += 1
        elif policy.startswith(("bind:", "prefer:", "interleave:")):
            counts["other_policy_mappings"] += 1
        else:
            counts["unclassified_policy_mappings"] += 1
    return counts


def _snapshot(stage: str, *, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        parent_affinity = sorted(os.sched_getaffinity(os.getppid()))
    except (AttributeError, OSError, ProcessLookupError):
        parent_affinity = None
    facts = {
        "stage": stage,
        "utc": datetime.now(UTC).isoformat(),
        "monotonic_seconds": time.monotonic(),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "affinity_cpus": sorted(os.sched_getaffinity(0)),
        "parent_affinity_cpus": parent_affinity,
        "current_rss_bytes": _proc_status_kb("VmRSS"),
        "current_swap_bytes": _proc_status_kb("VmSwap"),
        "process_peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024,
        "host_memory": _read_meminfo(),
        "numa_maps_policy_counts": _numa_maps_summary(),
    }
    payload.setdefault("stages", []).append(facts)
    _write_receipt(payload)
    print(f"[{facts['utc']}] QA stage: {stage}", flush=True)
    if facts["host_memory"].get("MemAvailable", 0) < HOST_AVAILABLE_FLOOR_BYTES:
        payload["status"] = "STOPPED_BELOW_HOST_AVAILABLE_FLOOR"
        payload["stop_reason"] = {
            "available_bytes": facts["host_memory"].get("MemAvailable"),
            "floor_bytes": HOST_AVAILABLE_FLOOR_BYTES,
            "detected_after_stage": stage,
        }
        _write_receipt(payload)
        raise SystemExit(73)
    return facts


def _write_receipt(payload: dict[str, Any]) -> None:
    target = Path(payload["receipt_path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_jsonable(payload), sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _module_hashes() -> dict[str, str]:
    relative_paths = (
        "src/common/config_3d.py",
        "src/common/gate_cd_materials.py",
        "src/common/materials.py",
        "src/constraints/floquet_3d.py",
        "src/geometry/mesh_builder_3d.py",
        "src/geometry/swept_hex_mesh.py",
        "src/geometry/task40_gate_cd_mesh_plan.py",
        "src/io/input_validation.py",
        "src/io/native_capacity_profile.py",
        "scripts/qa_task40_gate_cd_mesh_mpc.py",
    )
    return {relative: _sha256_file(ROOT / relative) for relative in relative_paths}


def run(
    receipt_path: Path,
    *,
    supervisor_cpu: int,
    worker_cpu: int,
    supervisor_pid: int,
    supervisor_start_ticks: int,
) -> dict[str, Any]:
    global _ACTIVE_PAYLOAD
    payload: dict[str, Any] = {
        "schema": "task40.gate-cd-live-mesh-mpc-qa.v1",
        "status": "RUNNING",
        "receipt_path": str(receipt_path.resolve()),
        "scope": {
            "mesh": "actual 27,600-cell mapped geometry and region tags",
            "materials": "DG0 epsilon map on every actual tagged cell",
            "space": "actual p6 hexahedral N1E function space",
            "periodic_constraints": "actual production double-Floquet MPC builder",
            "matrix_forms_factor_solve": "NOT_RUN_AND_NOT_BUILT",
            "visualization": "NOT_WRITTEN",
            "pss_uss_smaps": "NOT_READ",
        },
        "source_identity": {
            "git_head": _git_head(),
            "worktree_sha256_by_path": _module_hashes(),
        },
        "input_sha256": _sha256_file(INPUT),
        "environment_request": {
            "hwloc_components": os.environ.get("HWLOC_COMPONENTS"),
            "qualified_activation": os.environ.get("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION"),
            "pord64_activation": os.environ.get("TASK39EXTRA_PORD64_ACTIVATION"),
            "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
            "openblas_num_threads": os.environ.get("OPENBLAS_NUM_THREADS"),
            "mkl_num_threads": os.environ.get("MKL_NUM_THREADS"),
            "task_tmpdir": os.environ.get("TMPDIR"),
        },
        "resource_contract": {
            "host_available_floor_bytes": HOST_AVAILABLE_FLOOR_BYTES,
            "fixed_rss_cap_bytes": None,
            "swap": "observe_only",
            "pss_uss": "disabled",
            "worker_cpu_from_fresh": worker_cpu,
            "supervisor_cpu_from_fresh": supervisor_cpu,
            "numa_expected": "interleave:0-1",
        },
        "supervisor_anchor": {
            "pid": supervisor_pid,
            "start_ticks_from_fresh_process": supervisor_start_ticks,
        },
        "stages": [],
    }
    _ACTIVE_PAYLOAD = payload
    _write_receipt(payload)
    _snapshot("python_process_started", payload=payload)

    if os.environ.get("HWLOC_COMPONENTS") != "-x86":
        raise RuntimeError("this bounded host QA requires HWLOC_COMPONENTS=-x86")
    if os.environ.get("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("Task40 qualified activation is not active")
    if os.environ.get("TASK39EXTRA_PORD64_ACTIVATION") != "1":
        raise RuntimeError("qualified PORD64 activation is not active")
    affinity = sorted(os.sched_getaffinity(0))
    if affinity != [worker_cpu]:
        raise RuntimeError(
            f"QA worker must match fresh-selected CPU{worker_cpu}, got affinity {affinity}"
        )
    actual_supervisor_start_ticks = _proc_start_ticks(supervisor_pid)
    actual_supervisor_affinity = sorted(os.sched_getaffinity(supervisor_pid))
    payload["supervisor_anchor"].update(
        {
            "start_ticks_readback": actual_supervisor_start_ticks,
            "affinity_cpus_readback": actual_supervisor_affinity,
        }
    )
    _write_receipt(payload)
    if actual_supervisor_start_ticks != supervisor_start_ticks:
        raise RuntimeError("fresh-selected supervisor PID start_ticks identity changed")
    if actual_supervisor_affinity != [supervisor_cpu]:
        raise RuntimeError(
            "QA supervisor anchor affinity must match fresh-selected singleton CPU"
            f"{supervisor_cpu}, got {actual_supervisor_affinity}"
        )
    for variable in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        if os.environ.get(variable) != "1":
            raise RuntimeError(f"{variable} must be 1")

    import basix
    import dolfinx
    import dolfinx_mpc
    import mpi4py
    import petsc4py
    from basix.ufl import element
    from dolfinx import default_real_type, fem
    from mpi4py import MPI
    from petsc4py import PETSc

    from src.common.materials import relative_permittivity
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.geometry.task40_gate_cd_mesh_plan import (
        GATE_CD_REGION_TAGS,
        GATE_CD_STATIC_PLAN,
        gate_cd_live_mesh_facts,
    )
    from src.io.input_validation import (
        load_and_resolve,
        simulation_config_3d_from_normalized,
    )
    from src.io.resolved_config import resolved_config_sha256

    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError(f"bounded gate_cd QA requires MPI1, got {MPI.COMM_WORLD.size}")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError(f"expected PETSc complex128, got {PETSc.ScalarType}")
    if np.dtype(PETSc.IntType) != np.dtype(np.int64):
        raise RuntimeError(f"expected PORD64 PETSc.IntType, got {PETSc.IntType}")
    if np.dtype(default_real_type) != np.dtype(np.float64):
        raise RuntimeError(f"expected float64 DOLFINx geometry, got {default_real_type}")
    expected_petsc_root = (Path(os.environ["TASK39EXTRA_PORD64_ROOT"]) / "petsc").resolve()
    mapped_petsc_paths = sorted(
        {
            Path(line.split()[-1]).resolve().as_posix()
            for line in Path("/proc/self/maps").read_text(encoding="ascii").splitlines()
            if "libpetsc.so" in line and line.split()[-1].startswith("/")
        }
    )
    if not mapped_petsc_paths or any(
        not Path(path).is_relative_to(expected_petsc_root) for path in mapped_petsc_paths
    ):
        raise RuntimeError(
            "mapped PETSc library is not uniquely sourced from the qualified PORD64 overlay: "
            f"{mapped_petsc_paths!r}"
        )
    payload["abi"] = {
        "python": sys.executable,
        "mpi_library": MPI.Get_library_version().strip(),
        "mpi_size": int(MPI.COMM_WORLD.size),
        "petsc_version": list(PETSc.Sys.getVersion()),
        "petsc_scalar": str(np.dtype(PETSc.ScalarType)),
        "petsc_integer": str(np.dtype(PETSc.IntType)),
        "petsc_module": str(Path(petsc4py.__file__).resolve()),
        "petsc_lowlevel_module": str(Path(PETSc.__file__).resolve()),
        "mapped_libpetsc_paths": mapped_petsc_paths,
        "dolfinx_version": str(dolfinx.__version__),
        "dolfinx_module": str(Path(dolfinx.__file__).resolve()),
        "dolfinx_mpc_module": str(Path(dolfinx_mpc.__file__).resolve()),
        "basix_version": str(basix.__version__),
        "mpi4py_module": str(Path(mpi4py.__file__).resolve()),
        "default_real_type": str(np.dtype(default_real_type)),
    }
    _snapshot("qualified_abi_and_single_rank_verified", payload=payload)

    specification = load_and_resolve(INPUT)
    if specification.identity["run_id"] != "task40_gate_cd_0p7_mapped_p6_staged_v1":
        raise RuntimeError("staged input run identity changed")
    if specification.solver["native_capacity_profile"] != EXPECTED_PROFILE:
        raise RuntimeError("staged input resolved to the wrong gate_cd profile")
    resolved_payload = specification.as_jsonable()
    cfg = simulation_config_3d_from_normalized(resolved_payload)
    if cfg.geometry_kind != "task40_gate_cd_mapped" or cfg.nedelec_degree != 6:
        raise RuntimeError("resolved runtime config is not the staged mapped p6 case")
    payload["resolved_identity"] = {
        "model_id": specification.identity["model_id"],
        "run_id": specification.identity["run_id"],
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "resolved_config_sha256": resolved_config_sha256(specification),
        "expected_output_parent": str(specification.expected_output_parent),
        "geometry_kind": cfg.geometry_kind,
        "mesh_plan_id": cfg.mesh_plan_id,
        "mesh_plan_sha256": cfg.mesh_plan_sha256,
        "physical_region_count": len(cfg.physical_material_regions or ()),
    }
    if cfg.mesh_plan_sha256 != GATE_CD_STATIC_PLAN.plan_sha256:
        raise RuntimeError("resolved mapped geometry plan SHA changed")
    _snapshot("production_input_and_resolved_identity_verified", payload=payload)

    mesh_output_dir = Path(receipt_path).resolve().parent / "mesh_builder_scratch"
    mesh_data = build_airbox_mesh_3d(cfg, mesh_output_dir)
    mesh_facts = gate_cd_live_mesh_facts(
        mesh_data.mesh, mesh_data.cell_tags, GATE_CD_STATIC_PLAN
    )
    payload["live_mesh"] = {
        **mesh_facts,
        "mesh_cell_type_resolved": mesh_data.mesh_cell_type_resolved,
        "mesh_cells_resolved": list(mesh_data.mesh_cells_resolved),
        "mesh_spacing_mode_resolved": mesh_data.mesh_spacing_mode_resolved,
        "facet_tag_counts_by_tag": {
            str(tag): len(mesh_data.facet_tags.find(tag))
            for tag in (cfg.tags.x_min, cfg.tags.x_max, cfg.tags.y_min, cfg.tags.y_max, cfg.tags.z_min, cfg.tags.z_max)
        },
        "boundary_facets": len(mesh_data.boundary_facets),
        "vtk_outputs_written": False,
    }
    _snapshot("actual_mapped_mesh_tags_axes_and_positive_jacobian_verified", payload=payload)

    eps = relative_permittivity(mesh_data, cfg)
    eps_values = np.asarray(eps.x.array)
    if not np.all(np.isfinite(eps_values.real)) or not np.all(np.isfinite(eps_values.imag)):
        raise RuntimeError("actual DG0 epsilon map contains non-finite values")
    region_checks = {}
    for entry in cfg.physical_material_regions:
        tag = int(entry["tag"])
        cells = np.asarray(mesh_data.cell_tags.find(tag), dtype=np.int32)
        dofs = np.asarray(
            [eps.function_space.dofmap.cell_dofs(int(cell))[0] for cell in cells],
            dtype=np.int64,
        )
        actual = eps_values[dofs]
        expected = complex(entry["epsilon_r"])
        max_abs_error = float(np.max(np.abs(actual - expected)))
        if cells.size == 0 or max_abs_error != 0.0:
            raise RuntimeError(f"live DG0 epsilon assignment failed for {entry['label']}")
        region_checks[str(entry["label"])] = {
            "tag": tag,
            "cell_count": int(cells.size),
            "epsilon_r": [float(expected.real), float(expected.imag)],
            "max_abs_error": max_abs_error,
        }
    if len(region_checks) != len(GATE_CD_REGION_TAGS):
        raise RuntimeError("live DG0 check omitted one or more mapped material regions")
    payload["dg0_material_mapping"] = {
        "status": "PASS",
        "region_checks": region_checks,
        "coefficient_storage": {
            "shape": [int(value) for value in eps_values.shape],
            "dtype": str(eps_values.dtype),
            "sha256": hashlib.sha256(
                np.ascontiguousarray(eps_values).view(np.uint8).tobytes()
            ).hexdigest(),
        },
    }
    _snapshot("actual_dg0_epsilon_all_regions_verified", payload=payload)

    V = fem.functionspace(
        mesh_data.mesh,
        element("N1curl", mesh_data.mesh.basix_cell(), 6, dtype=default_real_type),
    )
    if V.dofmap.index_map_bs != 1:
        raise RuntimeError("actual p6 N1E space unexpectedly has a block dofmap")
    msh = mesh_data.mesh
    msh.topology.create_entity_permutations()
    cell_permutations = np.asarray(msh.topology.get_cell_permutation_info())
    element_basix = V.element.basix_element
    payload["p6_space"] = {
        "status": "BUILT_NO_FORM_NO_MATRIX",
        "family": str(element_basix.family.name),
        "degree": int(element_basix.degree),
        "lagrange_variant": str(element_basix.lagrange_variant.name),
        "basix_element_dimension": int(element_basix.dim),
        "global_dofs": int(V.dofmap.index_map.size_global),
        "local_dofs": int(V.dofmap.index_map.size_local),
        "ghost_dofs": int(V.dofmap.index_map.num_ghosts),
        "cell_count_global": int(msh.topology.index_map(msh.topology.dim).size_global),
        "cell_permutation_info": {
            "shape": [int(value) for value in cell_permutations.shape],
            "dtype": str(cell_permutations.dtype),
            "sha256": hashlib.sha256(
                np.ascontiguousarray(cell_permutations).view(np.uint8).tobytes()
            ).hexdigest(),
            "value_counts": {
                str(int(value)): int(count)
                for value, count in zip(*np.unique(cell_permutations, return_counts=True))
            },
        },
    }
    _snapshot("actual_p6_n1e_space_and_cell_orientation_map_built", payload=payload)

    floquet = build_double_floquet_mpc(V, mesh_data, cfg)
    if not bool(floquet.mpc.finalized):
        raise RuntimeError("production double-Floquet MPC did not finalize")
    pairing_error = float(floquet.max_face_pairing_coordinate_error)
    transform_fit_error = float(floquet.max_face_transform_fit_residual)
    edge_pairing_error = float(floquet.max_edge_midpoint_pairing_error)
    if not np.all(np.isfinite([pairing_error, transform_fit_error, edge_pairing_error])):
        raise RuntimeError("production MPC pairing/fit error contains a non-finite value")
    if pairing_error > MPC_PAIRING_COORDINATE_TOLERANCE:
        raise RuntimeError(
            "production MPC coordinate pairing error exceeds existing tolerance "
            f"{MPC_PAIRING_COORDINATE_TOLERANCE:.3e}: {pairing_error:.3e}"
        )
    if edge_pairing_error > MPC_PAIRING_COORDINATE_TOLERANCE:
        raise RuntimeError(
            "production MPC edge pairing error exceeds existing tolerance "
            f"{MPC_PAIRING_COORDINATE_TOLERANCE:.3e}: {edge_pairing_error:.3e}"
        )
    if transform_fit_error > MPC_FACE_TRANSFORM_FIT_TOLERANCE:
        raise RuntimeError(
            "production MPC face transform fit residual exceeds existing tolerance "
            f"{MPC_FACE_TRANSFORM_FIT_TOLERANCE:.3e}: {transform_fit_error:.3e}"
        )
    payload["production_mpc"] = {
        "status": "PASS",
        "constraint_mode_resolved": str(floquet.constraint_mode_resolved),
        "phase_x": [float(floquet.phase_x.real), float(floquet.phase_x.imag)],
        "phase_y": [float(floquet.phase_y.real), float(floquet.phase_y.imag)],
        "phase_corner": [float(floquet.phase_corner.real), float(floquet.phase_corner.imag)],
        "global_constraints": int(floquet.num_constraints),
        "local_slaves": int(floquet.num_local_slaves),
        "local_slave_records_seen": int(floquet.num_local_slave_records_seen),
        "x_constraints": int(floquet.num_x_constraints),
        "y_constraints": int(floquet.num_y_constraints),
        "corner_constraints": int(floquet.num_corner_constraints),
        "face_constraints": int(floquet.num_face_constraints),
        "max_masters_per_slave": int(floquet.max_masters_per_slave),
        "max_face_pairing_coordinate_error": float(floquet.max_face_pairing_coordinate_error),
        "max_edge_pairing_coordinate_error": float(floquet.max_edge_midpoint_pairing_error),
        "max_face_transform_fit_residual": float(floquet.max_face_transform_fit_residual),
        "existing_tolerance_checks": {
            "coordinate_pairing_and_edge_pairing_max_abs": MPC_PAIRING_COORDINATE_TOLERANCE,
            "face_transform_fit_max_abs": MPC_FACE_TRANSFORM_FIT_TOLERANCE,
            "finite": True,
            "status": "PASS",
        },
        "estimated_constraint_memory_mb": float(floquet.estimated_constraint_memory_mb),
        "used_full_boundary_gather": bool(floquet.used_full_boundary_gather),
        "created_dense_boundary_square": bool(floquet.created_dense_boundary_square),
        "topology_cache_hit": bool(floquet.topology_cache_hit),
        "topology_build_seconds_current": float(floquet.topology_build_seconds_current),
        "phase_update_seconds": float(floquet.phase_update_seconds),
        "timings_seconds": _jsonable(floquet.timings_seconds),
        "orientation_factor_stats": _jsonable(floquet.orientation_factor_stats),
        "mpc_finalized": True,
    }
    if payload["production_mpc"]["used_full_boundary_gather"] or payload["production_mpc"]["created_dense_boundary_square"]:
        raise RuntimeError("production MPC violated its sparse topology contract")
    _snapshot("actual_production_p6_double_floquet_mpc_complete", payload=payload)

    # The MPC Python wrapper has no public destroy() API. Dropping the owning
    # references and ending this one-shot process releases the no-solve QA data.
    del floquet, V, eps, mesh_data, cfg, specification
    import gc

    gc.collect()
    payload["status"] = "PASS_BOUNDED_GATE_CD_LIVE_MESH_MATERIAL_P6_SPACE_MPC_QA"
    payload["completion"] = {
        "global_variational_forms_compiled": False,
        "global_fe_matrix_assembled": False,
        "factor_created": False,
        "solve_called": False,
        "visualization_written": False,
        "factor_or_operator_cache_reuse": False,
    }
    final_snapshot = _snapshot("bounded_qa_complete_objects_released", payload=payload)
    if final_snapshot["numa_maps_policy_counts"]["interleave_0_1_mappings"] <= 0:
        raise RuntimeError("worker memory maps do not show the required interleave:0-1 policy")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--supervisor-cpu", type=int, required=True)
    parser.add_argument("--worker-cpu", type=int, required=True)
    parser.add_argument("--supervisor-pid", type=int, required=True)
    parser.add_argument("--supervisor-start-ticks", type=int, required=True)
    args = parser.parse_args()
    receipt_path = args.receipt.resolve()
    try:
        run(
            receipt_path,
            supervisor_cpu=args.supervisor_cpu,
            worker_cpu=args.worker_cpu,
            supervisor_pid=args.supervisor_pid,
            supervisor_start_ticks=args.supervisor_start_ticks,
        )
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1
    except BaseException as exc:
        payload = _ACTIVE_PAYLOAD or {
            "schema": "task40.gate-cd-live-mesh-mpc-qa.v1",
            "receipt_path": str(receipt_path),
            "stages": [],
        }
        payload["status"] = "FAILED_QA_STAGE"
        payload["error"] = {"type": type(exc).__name__, "message": str(exc)}
        payload["traceback"] = traceback.format_exc()
        _write_receipt(payload)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
