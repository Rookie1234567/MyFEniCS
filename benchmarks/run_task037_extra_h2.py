"""Narrow H2A exact-class inventory worker and resource checker.

This module is intentionally separate from the frozen Candidate-H runner.  It
only discovers the production full-space cell classes for the coercive proxy
``B0 = K_curl + k0**2 M_|epsilon|`` and inventories the reviewed exact-class
cache.  It does not implement a smoother, a constrained inverse, or a PDE
solve.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import numpy as np
import ufl
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task033_case090_pde_core import (
    attach_evidence_sha256,
    evidence_sha256_is_valid,
    inspect_tracked_source,
    read_json_object,
)
from benchmarks.run_task033_case090_watchdog import terminate_process_tree
from benchmarks.task034_wsl_resources import process_tree_sample
from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d_high_order import (
    clear_floquet_topology_cache,
    floquet_geometry_tolerance,
)
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
    _cell_tag_array,
)
from src.solvers.hcurl_exact_class_block_cache import (
    H2AClassBlockSpec,
    H2ACellReference,
    _key_json,
    build_task037_extra_h2a_block_cache,
    make_task037_extra_h2a_class_key,
    make_task037_extra_h2a_constraint_pattern,
    tabulate_task037_extra_h2a_cell_tensor,
)


ROOT = Path(__file__).resolve().parents[1]
H2A_SCHEMA = "task037.extra.h2a"
H2A_WORKER_SCHEMA = f"{H2A_SCHEMA}.worker.v1"
H2A_WATCHDOG_SCHEMA = f"{H2A_SCHEMA}.watchdog.v1"
H2A_CHECK_SCHEMA = f"{H2A_SCHEMA}.check.v1"
H2A_PROGRESS_SCHEMA = f"{H2A_SCHEMA}.progress.v1"
H2A_TIMEOUT_SECONDS = 1800.0
H2A_RSS_LIMIT_BYTES = 1_100_000_000
H2A_UNIQUE_CLASS_LIMIT = 32
H2A_FACTOR_PAYLOAD_LIMIT_BYTES = 400_000_000
H2A_FIXED_DEGREE = 6
H2A_FIXED_H_NM = 10.0
H2A_FIXED_GLOBAL_ROWS = 173_802
H2A_FIXED_CONSTRAINT_COUNT = 9_210


def _runtime_identity() -> dict[str, Any]:
    names = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )
    return {
        "qualified_activation": os.environ.get(
            "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
        ),
        "sys_executable": sys.executable,
        "threads": {name: os.environ.get(name) for name in names},
        "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
        "petsc_int_type": str(np.dtype(PETSc.IntType)),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            _jsonable(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _emit_marker(
    stream,
    *,
    event: str,
    started: float,
    rank: int,
    case: Mapping[str, Any] | None = None,
    class_id: int | None = None,
    local_rows: int | None = None,
    global_rows: int | None = None,
    cell_count: int | None = None,
) -> dict[str, Any]:
    marker = {
        "schema": H2A_PROGRESS_SCHEMA,
        "event": str(event),
        "elapsed_wall_seconds": float(time.perf_counter() - started),
        "rank": int(rank),
        "case": None if case is None else str(case.get("label")),
        "degree": None if case is None else int(case["degree"]),
        "h_nm": None if case is None else float(case["h_nm"]),
        "class_id": None if class_id is None else int(class_id),
        "cell_count": None if cell_count is None else int(cell_count),
        "local_rows": None if local_rows is None else int(local_rows),
        "global_rows": None if global_rows is None else int(global_rows),
    }
    line = json.dumps(marker, sort_keys=True, separators=(",", ":"))
    stream.write(line + "\n")
    stream.flush()
    print(line, flush=True)
    return marker


def _canonical_basis_signature(function_space) -> tuple[Any, ...]:
    element = function_space.element
    basix_element = element.basix_element
    layout = function_space.dofmap.dof_layout
    entity_signature = tuple(
        tuple(
            tuple(int(value) for value in layout.entity_dofs(dim, entity))
            for entity in range(len(basix_element.entity_dofs[dim]))
        )
        for dim in range(len(basix_element.entity_dofs))
    )
    return (
        "basix-canonical-local-basis-v1",
        str(getattr(basix_element, "family", "N1curl")),
        str(getattr(basix_element, "map_type", "identity")),
        int(element.space_dimension),
        entity_signature,
    )


def _material_identity(cfg, tag: int) -> tuple[Any, ...]:
    epsilon = _material_epsilon(cfg, tag)
    return (
        "epsilon_raw",
        epsilon,
        "epsilon_abs",
        float(abs(epsilon)),
        "mu_r",
        complex(cfg.mu_r),
        "curl_coefficient",
        complex(1.0 / cfg.mu_r),
    )


def _material_epsilon(cfg, tag: int) -> complex:
    epsilon_by_tag = {
        int(cfg.tags.air): complex(cfg.eps_air),
        int(cfg.tags.substrate): complex(cfg.eps_substrate),
        int(cfg.tags.grating): complex(cfg.eps_grating),
    }
    if int(tag) not in epsilon_by_tag:
        raise ValueError(f"H2A production cell tag is not a material tag: {tag}")
    return epsilon_by_tag[int(tag)]


def _proxy_identity(cfg) -> tuple[Any, ...]:
    return (
        "B0",
        "K_curl+k0^2*M_abs_epsilon",
        "k0",
        float(cfg.k0),
        "mu_r",
        complex(cfg.mu_r),
        "mass_coefficient",
        "unit-before-abs-epsilon",
    )


def _proxy_forms(function_space, mesh_data, cfg):
    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    dx = ufl.Measure("dx", domain=mesh_data.mesh)
    curl_form = (
        PETSc.ScalarType(1.0 / cfg.mu_r)
        * ufl.inner(ufl.curl(u), ufl.curl(v))
        * dx
    )
    mass_form = PETSc.ScalarType(1.0) * ufl.inner(u, v) * dx
    return fem.form(curl_form), fem.form(mass_form)


def _blocks_for_cell(blocks: Iterable[Any], cell_dofs: np.ndarray) -> tuple[Any, ...]:
    rows = {int(value) for value in np.asarray(cell_dofs, dtype=np.int64)}
    return tuple(
        block
        for block in blocks
        if block.slave_local_dofs
        and all(int(row) in rows for row in block.slave_local_dofs)
    )


def _discover_cell_references(
    function_space, mesh_data, cfg, floquet, *, geometry_tolerance: float
):
    mesh = mesh_data.mesh
    owned_cells = int(mesh.topology.index_map(mesh.topology.dim).size_local)
    tags = _cell_tag_array(mesh_data.cell_tags, owned_cells)
    mesh.topology.create_entity_permutations()
    cell_infos = np.asarray(
        mesh.topology.get_cell_permutation_info(), dtype=np.uint32
    )
    topology = floquet.phase_independent_topology
    if topology is None:
        raise RuntimeError("H2A production inventory requires Floquet topology")
    blocks = tuple(topology.blocks)
    basis_signature = _canonical_basis_signature(function_space)
    references: list[H2ACellReference] = []
    representatives: dict[tuple[Any, ...], dict[str, Any]] = {}
    for cell in range(owned_cells):
        cell_dofs = np.asarray(
            function_space.dofmap.cell_dofs(cell), dtype=np.int64
        )
        pattern = make_task037_extra_h2a_constraint_pattern(
            _blocks_for_cell(blocks, cell_dofs),
            cell_local_dofs=cell_dofs,
            phase_x=floquet.phase_x,
            phase_y=floquet.phase_y,
            phase_corner=floquet.phase_corner,
        )
        _coordinates, widths = _canonical_axis_aligned_coordinates(
            mesh, cell, tolerance=float(geometry_tolerance)
        )
        tag = int(tags[cell])
        key = make_task037_extra_h2a_class_key(
            cell_widths=widths,
            material_tag=tag,
            material_identity=_material_identity(cfg, tag),
            orientation=(int(cell_infos[cell]),),
            constraint_pattern=pattern,
            canonical_local_basis_signature=basis_signature,
            proxy_identity=_proxy_identity(cfg),
        )
        references.append(H2ACellReference(key, cell_dofs.copy()))
        representatives.setdefault(
            key,
            {
                "cell": int(cell),
                "tag": tag,
                "widths": widths,
                "cell_info": int(cell_infos[cell]),
                "pattern": pattern,
            },
        )
    return {
        "references": tuple(references),
        "representatives": representatives,
        "tags": tags,
        "basis_signature": basis_signature,
        "global_cell_count": int(mesh.comm.allreduce(owned_cells, op=MPI.SUM)),
    }


def _compact_cache_audit(audit: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "schema",
        "proxy",
        "unique_class_count",
        "unique_class_count_limit",
        "unique_class_gate_pass",
        "local_cell_count",
        "global_cell_count",
        "local_factor_count",
        "global_factor_count_sum",
        "global_unique_factor_count",
        "numeric_hash_dedup_count",
        "class_operator_spec_count",
        "class_operator_specs_retained",
        "cell_reference_count",
        "setup_temporary_dense_proxy_matrix_peak_bytes",
        "setup_borrowed_curl_mass_bytes_peak",
        "setup_lu_output_values_pivots_bytes_peak",
        "setup_lu_output_extra_bytes_peak",
        "setup_cache_visible_local_numeric_live_peak_bytes",
        "setup_cache_visible_local_retained_factor_bytes_before_peak",
        "setup_temporary_dense_proxy_matrix_retained",
        "per_cell_factor_count",
        "cell_factor_reference_count",
        "retained_numeric_payload_components",
        "retained_numeric_payload_local_bytes",
        "retained_numeric_payload_global_sum_bytes",
        "retained_numeric_payload_global_max_bytes",
        "retained_block_factor_payload_global_sum_bytes",
        "retained_block_factor_metadata_global_sum_bytes",
        "retained_block_factor_payload_with_metadata_global_sum_bytes",
        "retained_block_factor_payload_limit_bytes",
        "factor_payload_gate_pass",
        "factor_payload_gate_basis",
        "inventory_only",
        "constrained_smoother_implemented",
        "Bc_inverse_implemented",
        "constraint_pattern_semantics",
        "global_matrix_materialized",
        "global_constraint_matrix_materialized",
        "global_condensed_schur_materialized",
        "cell_schur_matrix_nnz",
        "slab_matrix_nnz",
        "slab_factor_count",
        "retained_dense_cell_matrix_count",
        "retained_original_dense_matrix_count",
        "original_dense_matrix_released_after_factorization",
        "ordinary_default_changed",
        "ksp_created",
        "dtn_used",
        "cell_class_ids",
        "cell_factor_ids",
        "factor_values_finite",
        "factor_pivots_finite",
        "deterministic_class_inventory_closed",
        "deterministic_class_inventory_sha256",
        "class_inventory",
    )
    return {field: _jsonable(audit[field]) for field in fields}


def _run_inventory_case(
    *,
    comm,
    case: Mapping[str, Any],
    run_dir: Path,
    marker_stream,
    started: float,
) -> dict[str, Any]:
    label = str(case["label"])
    cfg = target_stage4_config(
        degree=int(case["degree"]), h_nm=float(case["h_nm"])
    )
    case_dir = run_dir / "cases" / label
    _emit_marker(
        marker_stream,
        event="mesh_build_started",
        started=started,
        rank=comm.rank,
        case=case,
    )
    mesh_data = build_airbox_mesh_3d(cfg, case_dir / "mesh")
    _emit_marker(
        marker_stream,
        event="mesh_build_ready",
        started=started,
        rank=comm.rank,
        case=case,
        cell_count=int(mesh_data.mesh.topology.index_map(3).size_local),
    )
    _emit_marker(
        marker_stream,
        event="function_space_started",
        started=started,
        rank=comm.rank,
        case=case,
    )
    function_space = _create_nedelec_space(mesh_data.mesh, cfg)
    index_map = function_space.dofmap.index_map
    global_rows = int(index_map.size_global * function_space.dofmap.index_map_bs)
    local_rows = int(index_map.size_local * function_space.dofmap.index_map_bs)
    _emit_marker(
        marker_stream,
        event="function_space_ready",
        started=started,
        rank=comm.rank,
        case=case,
        cell_count=int(mesh_data.mesh.topology.index_map(3).size_local),
        local_rows=local_rows,
        global_rows=global_rows,
    )
    _emit_marker(
        marker_stream,
        event="floquet_mpc_started",
        started=started,
        rank=comm.rank,
        case=case,
        local_rows=local_rows,
        global_rows=global_rows,
    )
    floquet = build_double_floquet_mpc(function_space, mesh_data, cfg)
    _emit_marker(
        marker_stream,
        event="floquet_mpc_ready",
        started=started,
        rank=comm.rank,
        case=case,
        local_rows=local_rows,
        global_rows=global_rows,
    )
    _emit_marker(
        marker_stream,
        event="form_compile_started",
        started=started,
        rank=comm.rank,
        case=case,
        local_rows=local_rows,
        global_rows=global_rows,
    )
    curl_form, mass_form = _proxy_forms(function_space, mesh_data, cfg)
    _emit_marker(
        marker_stream,
        event="form_compile_ready",
        started=started,
        rank=comm.rank,
        case=case,
        local_rows=local_rows,
        global_rows=global_rows,
    )
    _emit_marker(
        marker_stream,
        event="key_discovery_started",
        started=started,
        rank=comm.rank,
        case=case,
        local_rows=local_rows,
        global_rows=global_rows,
    )
    geometry_tolerance = floquet_geometry_tolerance(cfg)
    discovery = _discover_cell_references(
        function_space,
        mesh_data,
        cfg,
        floquet,
        geometry_tolerance=geometry_tolerance,
    )
    representatives = discovery["representatives"]
    _emit_marker(
        marker_stream,
        event="key_discovery_ready",
        started=started,
        rank=comm.rank,
        case=case,
        cell_count=int(discovery["global_cell_count"]),
        local_rows=local_rows,
        global_rows=global_rows,
    )

    ordered_keys = tuple(sorted(representatives, key=_key_json))

    def class_specs() -> Iterable[H2AClassBlockSpec]:
        for class_id, key in enumerate(ordered_keys):
            representative = representatives[key]
            _emit_marker(
                marker_stream,
                event="class_factor_started",
                started=started,
                rank=comm.rank,
                case=case,
                class_id=class_id,
                cell_count=int(discovery["global_cell_count"]),
                local_rows=local_rows,
                global_rows=global_rows,
            )
            cell = int(representative["cell"])
            tag = int(representative["tag"])
            curl_tensor, widths, cell_info = tabulate_task037_extra_h2a_cell_tensor(
                curl_form,
                function_space,
                mesh_data.cell_tags,
                cell,
                geometry_tolerance=geometry_tolerance,
            )
            mass_tensor, mass_widths, mass_info = tabulate_task037_extra_h2a_cell_tensor(
                mass_form,
                function_space,
                mesh_data.cell_tags,
                cell,
                geometry_tolerance=geometry_tolerance,
            )
            if widths != mass_widths or cell_info != mass_info:
                raise RuntimeError("H2A curl/mass representative metadata differs")
            if widths != tuple(representative["widths"]):
                raise RuntimeError("H2A representative width changed during tabulation")
            if int(cell_info) != int(representative["cell_info"]):
                raise RuntimeError("H2A representative orientation changed during tabulation")
            yield H2AClassBlockSpec(
                class_key=key,
                curl_tensor=curl_tensor,
                mass_tensor=mass_tensor,
                k0=float(cfg.k0),
                abs_epsilon=float(abs(_material_epsilon(cfg, tag))),
            )
            del curl_tensor, mass_tensor
            _emit_marker(
                marker_stream,
                event="class_factor_ready",
                started=started,
                rank=comm.rank,
                case=case,
                class_id=class_id,
                cell_count=int(discovery["global_cell_count"]),
                local_rows=local_rows,
                global_rows=global_rows,
            )

    _emit_marker(
        marker_stream,
        event="cache_build_started",
        started=started,
        rank=comm.rank,
        case=case,
        cell_count=int(discovery["global_cell_count"]),
        local_rows=local_rows,
        global_rows=global_rows,
    )
    cache = build_task037_extra_h2a_block_cache(
        class_specs(),
        discovery["references"],
        comm=comm,
        task037_extra_h2a=True,
    )
    _emit_marker(
        marker_stream,
        event="cache_ready",
        started=started,
        rank=comm.rank,
        case=case,
        cell_count=int(discovery["global_cell_count"]),
        local_rows=local_rows,
        global_rows=global_rows,
    )
    try:
        audit = _compact_cache_audit(cache.audit)
        return {
            "label": label,
            "degree": int(case["degree"]),
            "h_nm": float(case["h_nm"]),
            "axis_cell_counts": [int(value) for value in mesh_data.mesh_cells_resolved],
            "global_cell_count": int(discovery["global_cell_count"]),
            "local_cell_count": int(mesh_data.mesh.topology.index_map(3).size_local),
            "local_rows": local_rows,
            "global_rows": global_rows,
            "constraint_count": int(floquet.num_constraints),
            "cache_audit": audit,
            "pattern_semantics": audit["constraint_pattern_semantics"],
        }
    finally:
        _emit_marker(
            marker_stream,
            event="cache_destroy_started",
            started=started,
            rank=comm.rank,
            case=case,
            cell_count=int(discovery["global_cell_count"]),
            local_rows=local_rows,
            global_rows=global_rows,
        )
        cache.destroy()
        clear_floquet_topology_cache()
        _emit_marker(
            marker_stream,
            event="cache_destroy_ready",
            started=started,
            rank=comm.rank,
            case=case,
            cell_count=int(discovery["global_cell_count"]),
            local_rows=local_rows,
            global_rows=global_rows,
        )


def _fixed_scope() -> dict[str, Any]:
    return {
        "degree": H2A_FIXED_DEGREE,
        "h_nm": H2A_FIXED_H_NM,
        "mpi_size": 1,
        "launch_mode": "mpi_singleton_direct",
        "operator": "B0=K_curl+k0^2*M_abs_epsilon",
        "inventory_only": True,
        "Bc_inverse_implemented": False,
        "timeout_seconds": H2A_TIMEOUT_SECONDS,
        "rss_limit_bytes": H2A_RSS_LIMIT_BYTES,
    }


def _h2a_worker_command(run_dir: Path, executable: str) -> list[str]:
    return [
        str(executable),
        "-m",
        "benchmarks.run_task037_extra_h2",
        "worker",
        "--run-dir",
        str(run_dir.resolve()),
    ]


def _run_worker(args: argparse.Namespace) -> int:
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / "run_summary.json"
    progress_path = run_dir / "progress.jsonl"
    source_at_start = inspect_tracked_source(ROOT)
    started = time.perf_counter()
    cases = (
        {"label": "p6_h10", "degree": 6, "h_nm": 10.0},
        {"label": "p2_h10", "degree": 2, "h_nm": 10.0},
        {"label": "p2_h5", "degree": 2, "h_nm": 5.0},
    )
    results: list[dict[str, Any]] = []
    error: str | None = None
    if comm.size != 1:
        error = f"H2A worker is fixed to MPI1, got {comm.size}"
    try:
        with progress_path.open("w", encoding="utf-8") as marker_stream:
            if error is None:
                for case in cases:
                    results.append(
                        _run_inventory_case(
                            comm=comm,
                            case=case,
                            run_dir=run_dir,
                            marker_stream=marker_stream,
                            started=started,
                        )
                    )
            _emit_marker(
                marker_stream,
                event="summary_started",
                started=started,
                rank=comm.rank,
                local_rows=(None if not results else results[0]["local_rows"]),
                global_rows=(None if not results else results[0]["global_rows"]),
            )
    except (OSError, RuntimeError, ValueError, TypeError, IndexError, KeyError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    source_at_end = inspect_tracked_source(ROOT)
    scope = _fixed_scope()
    refinement = None
    if len(results) == 3:
        p2_h10 = results[1]
        p2_h5 = results[2]
        refinement = {
            "coarse": {
                "label": p2_h10["label"],
                "global_cell_count": p2_h10["global_cell_count"],
                "unique_class_count": p2_h10["cache_audit"]["unique_class_count"],
            },
            "refined": {
                "label": p2_h5["label"],
                "global_cell_count": p2_h5["global_cell_count"],
                "unique_class_count": p2_h5["cache_audit"]["unique_class_count"],
            },
        }
    payload = {
        "schema": H2A_WORKER_SCHEMA,
        "status": "measurement_complete" if error is None else "gate_failed",
        "scope": scope,
        "source_at_start": source_at_start.as_jsonable(),
        "source_at_end": source_at_end.as_jsonable(),
        "runtime_identity": _runtime_identity(),
        "cases": results,
        "refinement": refinement,
        "inventory_only": True,
        "Bc_inverse_implemented": False,
        "error": error,
        "elapsed_wall_seconds": float(time.perf_counter() - started),
    }
    payload = attach_evidence_sha256(payload)
    if comm.rank == 0:
        _write_json(summary_path, payload)
    return int(comm.bcast(0 if error is None else 1, root=0))


def _runtime_identity_is_qualified(identity: Any) -> bool:
    if not isinstance(identity, Mapping):
        return False
    executable = identity.get("sys_executable")
    threads = identity.get("threads")
    executable_path = Path(executable) if isinstance(executable, str) else None
    qualified_venv = (ROOT / ".venv").resolve()
    return bool(
        identity.get("qualified_activation") == "1"
        and executable_path is not None
        and executable_path.is_absolute()
        and executable_path.name == "python"
        and executable_path.parent.name == "bin"
        and executable_path.parent.parent.resolve() == qualified_venv
        and "\\" not in str(executable_path)
        and identity.get("petsc_scalar_type") == "complex128"
        and identity.get("petsc_int_type") == "int32"
        and isinstance(threads, Mapping)
        and all(threads.get(name) == "1" for name in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        ))
    )


def _inventory_digest_is_closed(audit: Mapping[str, Any]) -> bool:
    class_inventory = audit.get("class_inventory")
    cell_class_ids = audit.get("cell_class_ids")
    cell_factor_ids = audit.get("cell_factor_ids")
    observed_digest = audit.get("deterministic_class_inventory_sha256")
    if (
        not isinstance(class_inventory, list)
        or not isinstance(cell_class_ids, list)
        or not isinstance(cell_factor_ids, list)
    ):
        return False
    if not isinstance(observed_digest, str) or len(observed_digest) != 64:
        return False
    if any(
        not isinstance(item, Mapping)
        or not isinstance(item.get("class_id"), int)
        or not isinstance(item.get("factor_id"), int)
        or not isinstance(item.get("class_key_sha256"), str)
        or len(item["class_key_sha256"]) != 64
        or not isinstance(item.get("numeric_tensor_sha256"), str)
        or len(item["numeric_tensor_sha256"]) != 64
        for item in class_inventory
    ):
        return False
    if tuple(item["class_id"] for item in class_inventory) != tuple(range(len(class_inventory))):
        return False
    if any(
        not isinstance(value, int)
        or value < 0
        or value >= len(class_inventory)
        for value in cell_class_ids
    ):
        return False
    factor_ids = tuple(item["factor_id"] for item in class_inventory)
    factor_count = max(factor_ids, default=-1) + 1
    if set(factor_ids) != set(range(factor_count)):
        return False
    if any(
        not isinstance(value, int) or value < 0 or value >= factor_count
        for value in cell_factor_ids
    ):
        return False
    if len(cell_class_ids) != len(cell_factor_ids) or any(
        cell_factor_ids[index]
        != class_inventory[cell_class_ids[index]]["factor_id"]
        for index in range(len(cell_class_ids))
    ):
        return False
    digest = hashlib.sha256(
        _key_json(
            (
                tuple(class_inventory),
                tuple(int(value) for value in cell_class_ids),
                tuple(int(value) for value in cell_factor_ids),
            )
        ).encode("utf-8")
    ).hexdigest()
    return digest == observed_digest


def _evaluate_h2a_worker_qualification(
    raw: Mapping[str, Any],
) -> dict[str, Any]:
    problems: list[str] = []
    if raw.get("schema") != H2A_WORKER_SCHEMA:
        problems.append("schema")
    if raw.get("status") != "measurement_complete":
        problems.append("status")
    if raw.get("error") is not None:
        problems.append("error")
    if raw.get("inventory_only") is not True:
        problems.append("inventory_only")
    if raw.get("Bc_inverse_implemented") is not False:
        problems.append("Bc_inverse_implemented")
    if not _runtime_identity_is_qualified(raw.get("runtime_identity")):
        problems.append("runtime_identity")
    scope = raw.get("scope")
    if not isinstance(scope, Mapping):
        problems.append("scope")
    else:
        for field, expected in _fixed_scope().items():
            if scope.get(field) != expected:
                problems.append(f"scope.{field}")
    start = raw.get("source_at_start")
    end = raw.get("source_at_end")
    for label, identity in (("source_at_start", start), ("source_at_end", end)):
        if not isinstance(identity, Mapping):
            problems.append(label)
            continue
        if (
            identity.get("tracked_source_dirty") is not False
            or identity.get("source_worktree_dirty") is not False
        ):
            problems.append(f"{label}.dirty")
        if (
            identity.get("nonignored_untracked_paths") != []
            or identity.get("worktree_status_porcelain") != []
        ):
            problems.append(f"{label}.worktree")
        if identity.get("git_error") is not None:
            problems.append(f"{label}.git_error")
        sha = identity.get("source_commit_full_sha")
        if not isinstance(sha, str) or len(sha) != 40:
            problems.append(f"{label}.sha")
    if (
        isinstance(start, Mapping)
        and isinstance(end, Mapping)
        and start.get("source_commit_full_sha")
        != end.get("source_commit_full_sha")
    ):
        problems.append("source.not_stable")
    cases = raw.get("cases")
    expected_cases = {
        "p6_h10": (6, 10.0),
        "p2_h10": (2, 10.0),
        "p2_h5": (2, 5.0),
    }
    case_map: dict[str, Mapping[str, Any]] = {}
    if not isinstance(cases, list) or len(cases) != len(expected_cases):
        problems.append("cases.identity")
    else:
        for case in cases:
            if not isinstance(case, Mapping):
                problems.append("cases.identity")
                continue
            label = case.get("label")
            expected = expected_cases.get(label)
            if expected is None or (
                case.get("degree") != expected[0]
                or case.get("h_nm") != expected[1]
                or label in case_map
            ):
                problems.append("cases.identity")
            else:
                case_map[str(label)] = case
    if set(case_map) != set(expected_cases):
        problems.append("cases.identity")
    for label, case in case_map.items():
        audit = case.get("cache_audit")
        if not isinstance(audit, Mapping):
            problems.append(f"{label}.cache_audit")
        else:
            if case.get("global_cell_count") != audit.get("global_cell_count"):
                problems.append(f"{label}.global_cell_count")
            count = audit.get("unique_class_count")
            if (
                not isinstance(count, int)
                or isinstance(count, bool)
                or count < 1
                or count > H2A_UNIQUE_CLASS_LIMIT
            ):
                problems.append(f"{label}.unique_class_count")
            if (
                not isinstance(audit.get("class_inventory"), list)
                or count != len(audit["class_inventory"])
                or not _inventory_digest_is_closed(audit)
            ):
                problems.append(f"{label}.inventory_closure")
        if label == "p6_h10" and isinstance(audit, Mapping):
            payload = audit.get("retained_block_factor_payload_with_metadata_global_sum_bytes")
            components = audit.get("retained_numeric_payload_components")
            if not isinstance(count, int) or count > H2A_UNIQUE_CLASS_LIMIT:
                problems.append("unique_class_count")
            if (
                not isinstance(case.get("global_rows"), int)
                or isinstance(case.get("global_rows"), bool)
                or case["global_rows"] != H2A_FIXED_GLOBAL_ROWS
            ):
                problems.append("global_rows")
            if case.get("constraint_count") != H2A_FIXED_CONSTRAINT_COUNT:
                problems.append("constraint_count")
            for field in (
                "global_unique_factor_count",
                "global_factor_count_sum",
                "numeric_hash_dedup_count",
                "retained_numeric_payload_global_sum_bytes",
            ):
                value = audit.get(field)
                if (
                    not isinstance(value, int)
                    or isinstance(value, bool)
                    or value < 0
                    or (
                        field != "retained_numeric_payload_global_sum_bytes"
                        and value > count
                    )
                ):
                    problems.append(f"audit.{field}")
            if (
                not isinstance(payload, int)
                or payload < 0
                or payload > H2A_FACTOR_PAYLOAD_LIMIT_BYTES
            ):
                problems.append("resident_factor_payload")
            if not isinstance(components, Mapping) or any(
                not isinstance(value, int) or isinstance(value, bool) or value < 0
                for value in components.values()
            ):
                problems.append("payload_components")
            global_unique_factor_count = audit.get("global_unique_factor_count")
            numeric_hash_dedup_count = audit.get("numeric_hash_dedup_count")
            global_factor_count_sum = audit.get("global_factor_count_sum")
            if (
                not all(
                    isinstance(value, int) and not isinstance(value, bool)
                    for value in (
                        global_unique_factor_count,
                        numeric_hash_dedup_count,
                        global_factor_count_sum,
                    )
                )
                or global_unique_factor_count + numeric_hash_dedup_count != count
                or global_factor_count_sum != global_unique_factor_count
            ):
                problems.append("factor_count_closure")
            inventory = audit.get("class_inventory")
            if isinstance(inventory, list):
                factor_ids = {
                    item.get("factor_id")
                    for item in inventory
                    if isinstance(item, Mapping)
                }
                if global_unique_factor_count != len(factor_ids):
                    problems.append("factor_inventory_count")
            for field, expected in {
                "global_matrix_materialized": False,
                "global_constraint_matrix_materialized": False,
                "global_condensed_schur_materialized": False,
                "cell_schur_matrix_nnz": 0,
                "slab_matrix_nnz": 0,
                "retained_dense_cell_matrix_count": 0,
                "per_cell_factor_count": 0,
                "slab_factor_count": 0,
                "ksp_created": False,
                "dtn_used": False,
                "inventory_only": True,
                "Bc_inverse_implemented": False,
                "ordinary_default_changed": False,
                "factor_values_finite": True,
                "factor_pivots_finite": True,
                "deterministic_class_inventory_closed": True,
            }.items():
                if audit.get(field) != expected:
                    problems.append(f"audit.{field}")
    refinement = raw.get("refinement")
    if not isinstance(refinement, Mapping):
        problems.append("refinement")
    else:
        coarse = refinement.get("coarse")
        refined = refinement.get("refined")
        if not isinstance(coarse, Mapping) or not isinstance(refined, Mapping):
            problems.append("refinement.counts")
        else:
            coarse_case = case_map.get("p2_h10")
            refined_case = case_map.get("p2_h5")
            coarse_cells = coarse.get("global_cell_count")
            refined_cells = refined.get("global_cell_count")
            coarse_classes = coarse.get("unique_class_count")
            refined_classes = refined.get("unique_class_count")
            if not isinstance(coarse_case, Mapping) or not isinstance(refined_case, Mapping):
                problems.append("refinement.binding")
                coarse_case_audit = refined_case_audit = None
            else:
                coarse_case_audit = coarse_case.get("cache_audit")
                refined_case_audit = refined_case.get("cache_audit")
                if (
                    not isinstance(coarse_case_audit, Mapping)
                    or not isinstance(refined_case_audit, Mapping)
                    or coarse.get("label") != "p2_h10"
                    or refined.get("label") != "p2_h5"
                    or coarse_cells != coarse_case.get("global_cell_count")
                    or refined_cells != refined_case.get("global_cell_count")
                    or (
                        isinstance(coarse_case_audit, Mapping)
                        and coarse_classes
                        != coarse_case_audit.get("unique_class_count")
                    )
                    or (
                        isinstance(refined_case_audit, Mapping)
                        and refined_classes
                        != refined_case_audit.get("unique_class_count")
                    )
                ):
                    problems.append("refinement.binding")
            valid_counts = all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 1
                for value in (coarse_cells, refined_cells, coarse_classes, refined_classes)
            )
            if (
                not valid_counts
                or refined_cells <= coarse_cells
                or coarse_classes > H2A_UNIQUE_CLASS_LIMIT
                or refined_classes > H2A_UNIQUE_CLASS_LIMIT
            ):
                problems.append("refinement.counts")
            elif refined_classes * coarse_cells >= coarse_classes * refined_cells:
                problems.append("refinement.class_growth")
    return {
        "schema": "task037.extra.h2a.worker.qualification.v1",
        "pass": not problems,
        "problems": problems,
    }


def _timeline_metrics(path: Path) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                samples.append(json.loads(line))
    live = [sample for sample in samples if sample.get("sample_kind") == "worker"]
    if not live:
        return {
            "readable": False,
            "live_sample_count": 0,
            "peak_rss_bytes": None,
            "swap_bytes": None,
        }
    rss_values = [sample.get("rss_bytes") for sample in live]
    swap_values = [sample.get("swap_bytes") for sample in live]
    readable = all(
        isinstance(sample.get("rss_bytes"), int)
        and sample["rss_bytes"] >= 0
        and isinstance(sample.get("swap_bytes"), int)
        and sample["swap_bytes"] >= 0
        and sample.get("all_status_readable") is True
        for sample in live
    )
    return {
        "readable": readable,
        "live_sample_count": len(live),
        "peak_rss_bytes": (
            max(rss_values)
            if all(isinstance(value, int) for value in rss_values)
            else None
        ),
        "swap_bytes": (
            max(swap_values)
            if all(isinstance(value, int) for value in swap_values)
            else None
        ),
    }


def _h2a_compact_measurements(
    worker: Mapping[str, Any],
    watchdog: Mapping[str, Any],
    timeline: Mapping[str, Any],
) -> dict[str, Any]:
    cases = worker["cases"]
    by_label = {str(case["label"]): case for case in cases}
    p6 = by_label["p6_h10"]
    p2_h10 = by_label["p2_h10"]
    p2_h5 = by_label["p2_h5"]
    p6_audit = p6["cache_audit"]
    coarse_cells = p2_h10["global_cell_count"]
    refined_cells = p2_h5["global_cell_count"]
    coarse_classes = p2_h10["cache_audit"]["unique_class_count"]
    refined_classes = p2_h5["cache_audit"]["unique_class_count"]
    ratio = (refined_classes * coarse_cells) / (
        coarse_classes * refined_cells
    )
    return {
        "source_commit_full_sha": worker["source_at_start"]["source_commit_full_sha"],
        "runtime_identity": worker["runtime_identity"],
        "mpi_size": worker["scope"]["mpi_size"],
        "p6_h10": {
            "degree": p6["degree"],
            "h_nm": p6["h_nm"],
            "global_rows": p6["global_rows"],
            "constraint_count": p6["constraint_count"],
            "global_cell_count": p6["global_cell_count"],
            "unique_class_count": p6_audit["unique_class_count"],
            "global_unique_factor_count": p6_audit["global_unique_factor_count"],
            "numeric_hash_dedup_count": p6_audit["numeric_hash_dedup_count"],
            "retained_block_factor_payload_with_metadata_global_sum_bytes": p6_audit[
                "retained_block_factor_payload_with_metadata_global_sum_bytes"
            ],
            "retained_numeric_payload_global_sum_bytes": p6_audit[
                "retained_numeric_payload_global_sum_bytes"
            ],
            "inventory_digest": p6_audit[
                "deterministic_class_inventory_sha256"
            ],
            "finite": bool(
                p6_audit["factor_values_finite"]
                and p6_audit["factor_pivots_finite"]
            ),
        },
        "p2_h10": {
            "global_cell_count": coarse_cells,
            "unique_class_count": coarse_classes,
        },
        "p2_h5": {
            "global_cell_count": refined_cells,
            "unique_class_count": refined_classes,
        },
        "refinement": {
            "coarse_label": "p2_h10",
            "refined_label": "p2_h5",
            "class_growth_over_cell_growth": ratio,
            "class_growth_strictly_sublinear": (
                refined_classes * coarse_cells < coarse_classes * refined_cells
            ),
        },
        "process_tree": {
            "peak_rss_bytes": timeline["peak_rss_bytes"],
            "swap_bytes": timeline["swap_bytes"],
            "elapsed_wall_seconds": watchdog["completion_elapsed_seconds"],
            "termination": watchdog["termination"],
            "live_sample_count": timeline["live_sample_count"],
        },
    }


def _h2a_terminate_process_tree(process: subprocess.Popen[Any]) -> dict[str, Any]:
    """Use the repository watchdog's process-group termination authority."""

    return terminate_process_tree(process, grace_seconds=5.0)


def _check_h2a_raw(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    worker_path = run_dir / "run_summary.json"
    watchdog_path = run_dir / "watchdog_summary.json"
    timeline_path = run_dir / "watchdog_timeline.jsonl"
    worker = read_json_object(worker_path)
    watchdog = read_json_object(watchdog_path)
    worker_eval = _evaluate_h2a_worker_qualification(worker)
    timeline = _timeline_metrics(timeline_path)
    worker_runtime = worker.get("runtime_identity")
    watchdog_runtime = watchdog.get("runtime_identity")
    command = watchdog.get("command")
    watchdog_checks = {
        "schema": watchdog.get("schema") == H2A_WATCHDOG_SCHEMA,
        "status": watchdog.get("status") == "pass",
        "worker_evidence_valid": evidence_sha256_is_valid(worker),
        "watchdog_evidence_valid": evidence_sha256_is_valid(watchdog),
        "worker_qualification_pass": worker_eval["pass"],
        "runtime_identity_qualified": _runtime_identity_is_qualified(
            watchdog_runtime
        ),
        "runtime_identity_match": watchdog_runtime == worker_runtime,
        "command_runtime_identity": (
            isinstance(command, list)
            and len(command) == 6
            and isinstance(watchdog_runtime, Mapping)
            and command[0] == watchdog_runtime.get("sys_executable")
            and command[1:5]
            == [
                "-m",
                "benchmarks.run_task037_extra_h2",
                "worker",
                "--run-dir",
            ]
            and isinstance(command[5], str)
            and Path(command[5]).resolve() == run_dir
        ),
        "source_clean_and_stable": watchdog.get("source_clean_and_stable") is True,
        "source_pair_matches_worker": (
            watchdog.get("source_at_start") == worker.get("source_at_start")
            and watchdog.get("source_at_end") == worker.get("source_at_end")
        ),
        "timeline_readable": timeline["readable"],
        "timeline_has_live_samples": timeline["live_sample_count"] > 0,
        "timeline_peak_within_limit": isinstance(timeline["peak_rss_bytes"], int)
        and timeline["peak_rss_bytes"] <= H2A_RSS_LIMIT_BYTES,
        "timeline_swap_zero": timeline["swap_bytes"] == 0,
        "watchdog_peak_matches_timeline": (
            isinstance(watchdog.get("process_tree_peak_rss_bytes"), int)
            and not isinstance(watchdog.get("process_tree_peak_rss_bytes"), bool)
            and watchdog["process_tree_peak_rss_bytes"]
            == timeline["peak_rss_bytes"]
        ),
        "watchdog_swap_matches_timeline": (
            isinstance(watchdog.get("process_tree_swap_bytes"), int)
            and not isinstance(watchdog.get("process_tree_swap_bytes"), bool)
            and watchdog["process_tree_swap_bytes"] == timeline["swap_bytes"]
        ),
        "termination_none": watchdog.get("termination") is None,
        "completion_elapsed_valid": (
            isinstance(watchdog.get("completion_elapsed_seconds"), (int, float))
            and not isinstance(watchdog.get("completion_elapsed_seconds"), bool)
            and np.isfinite(watchdog["completion_elapsed_seconds"])
            and watchdog["completion_elapsed_seconds"] >= 0.0
        ),
        "return_code_zero": watchdog.get("return_code") == 0,
    }
    checks = {
        **watchdog_checks,
        "worker_qualification": worker_eval["pass"],
    }
    problems = list(worker_eval["problems"])
    problems.extend(field for field, passed in watchdog_checks.items() if not passed)
    measurements = None
    if not problems:
        try:
            measurements = _h2a_compact_measurements(
                worker, watchdog, timeline
            )
        except (KeyError, TypeError, ValueError):
            problems.append("measurements")
    return {
        "schema": H2A_CHECK_SCHEMA,
        "status": "pass" if not problems else "gate_failed",
        "pass": not problems,
        "problems": sorted(set(problems)),
        "worker_qualification": worker_eval,
        "watchdog_checks": checks,
        "timeline": timeline,
        "measurements": measurements,
        "raw_artifacts": {
            name: {
                "path": path.name,
                "sha256": _sha256_file(path),
                "bytes": int(path.stat().st_size),
            }
            for name, path in {
                "run_summary": worker_path,
                "watchdog_summary": watchdog_path,
                "watchdog_timeline": timeline_path,
            }.items()
        },
    }


def _run_watchdog(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    timeline_path = run_dir / "watchdog_timeline.jsonl"
    watchdog_path = run_dir / "watchdog_summary.json"
    stdout_path = run_dir / "worker_stdout.txt"
    root_pid_path = run_dir / "root_pid.json"
    source_at_start = inspect_tracked_source(ROOT)
    command = _h2a_worker_command(run_dir, sys.executable)
    started = time.perf_counter()
    samples: list[dict[str, Any]] = []
    process: subprocess.Popen[Any] | None = None
    termination: str | None = None
    return_code: int | None = None
    with stdout_path.open("w", encoding="utf-8") as stdout, timeline_path.open(
        "w", encoding="utf-8"
    ) as timeline_stream:
        if source_at_start.tracked_source_dirty or source_at_start.nonignored_untracked_paths:
            termination = "source_not_clean"
        else:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=stdout,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            _write_json(
                root_pid_path,
                {"schema": f"{H2A_SCHEMA}.root.v1", "root_pid": int(process.pid)},
            )
        while process is not None and process.poll() is None:
            observed = process_tree_sample(process.pid)
            sample = {
                "schema": H2A_PROGRESS_SCHEMA,
                "sample_kind": "worker",
                "elapsed_wall_seconds": float(time.perf_counter() - started),
                "root_pid": int(process.pid),
                "pids": [int(pid) for pid in observed.pids],
                "rss_bytes": int(observed.rss_bytes),
                "swap_bytes": int(observed.swap_bytes),
                "all_status_readable": bool(observed.all_status_readable),
            }
            samples.append(sample)
            timeline_stream.write(json.dumps(sample, sort_keys=True) + "\n")
            timeline_stream.flush()
            if not observed.all_status_readable:
                termination = "authority_unreadable"
            elif observed.swap_bytes > 0:
                termination = "nonzero_swap"
            elif observed.rss_bytes > H2A_RSS_LIMIT_BYTES:
                termination = "process_tree_rss_over_1.1e9_bytes"
            elif sample["elapsed_wall_seconds"] >= H2A_TIMEOUT_SECONDS:
                termination = "wall_timeout"
            if termination is not None:
                _h2a_terminate_process_tree(process)
                break
            time.sleep(0.25)
        if process is not None:
            return_code = process.wait()
        final = {
            "schema": H2A_PROGRESS_SCHEMA,
            "sample_kind": "final",
            "elapsed_wall_seconds": float(time.perf_counter() - started),
            "return_code": return_code,
        }
        timeline_stream.write(json.dumps(final, sort_keys=True) + "\n")
        timeline_stream.flush()
    source_at_end = inspect_tracked_source(ROOT)
    worker_path = run_dir / "run_summary.json"
    worker = read_json_object(worker_path) if worker_path.is_file() else None
    worker_valid = isinstance(worker, Mapping) and evidence_sha256_is_valid(worker)
    worker_qualification = (
        _evaluate_h2a_worker_qualification(worker)
        if isinstance(worker, Mapping)
        else {"pass": False, "problems": ["worker summary missing"]}
    )
    live_peak = max((sample["rss_bytes"] for sample in samples), default=None)
    swap = max((sample["swap_bytes"] for sample in samples), default=None)
    source_clean = (
        source_at_start.source_commit_full_sha is not None
        and source_at_start.source_commit_full_sha == source_at_end.source_commit_full_sha
        and not source_at_start.tracked_source_dirty
        and not source_at_end.tracked_source_dirty
        and not source_at_start.nonignored_untracked_paths
        and not source_at_end.nonignored_untracked_paths
    )
    status = (
        termination is None
        and return_code == 0
        and worker_valid
        and worker_qualification["pass"]
        and source_clean
        and isinstance(live_peak, int)
        and live_peak <= H2A_RSS_LIMIT_BYTES
        and swap == 0
    )
    payload = attach_evidence_sha256(
        {
            "schema": H2A_WATCHDOG_SCHEMA,
            "status": "pass" if status else "gate_failed",
            "run_dir": str(run_dir),
            "command": command,
            "scope": _fixed_scope(),
            "runtime_identity": _runtime_identity(),
            "source_at_start": source_at_start.as_jsonable(),
            "source_at_end": source_at_end.as_jsonable(),
            "source_clean_and_stable": source_clean,
            "return_code": return_code,
            "termination": termination,
            "completion_elapsed_seconds": float(time.perf_counter() - started),
            "live_sample_count": len(samples),
            "process_tree_peak_rss_bytes": live_peak,
            "process_tree_swap_bytes": swap,
            "worker_summary_present": isinstance(worker, Mapping),
            "worker_evidence_valid": worker_valid,
            "worker_qualification_pass": worker_qualification["pass"],
            "worker_qualification_problems": worker_qualification["problems"],
            "raw_artifacts": {
                "worker_stdout.txt": {
                    "path": str(stdout_path),
                    "sha256": _sha256_file(stdout_path),
                    "bytes": int(stdout_path.stat().st_size),
                },
                "watchdog_timeline.jsonl": {
                    "path": str(timeline_path),
                    "sha256": _sha256_file(timeline_path),
                    "bytes": int(timeline_path.stat().st_size),
                },
                "run_summary.json": (
                    {
                        "path": str(worker_path),
                        "sha256": _sha256_file(worker_path),
                        "bytes": int(worker_path.stat().st_size),
                    }
                    if worker_path.is_file()
                    else None
                ),
            },
        }
    )
    _write_json(watchdog_path, payload)
    print(f"H2A watchdog status={payload['status']} run_dir={run_dir}", flush=True)
    return 0 if status else 1


def _run_check(args: argparse.Namespace) -> int:
    try:
        result = _check_h2a_raw(Path(args.run_dir))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        result = {
            "schema": H2A_CHECK_SCHEMA,
            "status": "gate_failed",
            "pass": False,
            "problems": [f"raw_unreadable:{type(exc).__name__}"],
        }
    output = Path(args.output).resolve()
    _write_json(output, attach_evidence_sha256(result))
    print(f"H2A check status={result['status']} output={output}", flush=True)
    return 0 if result["pass"] else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    worker = sub.add_parser("worker")
    worker.add_argument("--run-dir", required=True)
    worker.set_defaults(handler=_run_worker)
    watchdog = sub.add_parser("watchdog")
    watchdog.add_argument("--run-dir", required=True)
    watchdog.set_defaults(handler=_run_watchdog)
    checker = sub.add_parser("check")
    checker.add_argument("--run-dir", required=True)
    checker.add_argument("--output", required=True)
    checker.set_defaults(handler=_run_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
