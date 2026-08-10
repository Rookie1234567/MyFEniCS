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
import gc
import hashlib
import json
import os
import platform
from pathlib import Path
import shlex
import subprocess
import sys
import sysconfig
import time
from typing import Any

import numpy as np
import ufl
import basix
import dolfinx
import ffcx
import ffcx.codegeneration
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
H2A_FORM_JIT_EXTRA_COMPILE_ARGS = ("-O0", "-g0")

R0_SCHEMA = "task037.extra.h2a.r0"
R0_WORKER_SCHEMA = f"{R0_SCHEMA}.worker.v1"
R0_WATCHDOG_SCHEMA = f"{R0_SCHEMA}.watchdog.v1"
R0_CHECK_SCHEMA = f"{R0_SCHEMA}.check.v1"
R0_PROGRESS_SCHEMA = f"{R0_SCHEMA}.progress.v1"
R0_TIMEOUT_SECONDS = 1800.0
R0_RSS_LIMIT_BYTES = 1_000_000_000
R0_CASES = (
    ("p6_h10", 6, 10.0),
    ("p2_h10", 2, 10.0),
    ("p2_h5", 2, 5.0),
)
R0_FORBIDDEN_IDENTITY_WORDS = (
    "global_row",
    "local_row",
    "owner",
    "cell_id",
    "coordinate",
    "geometry_key",
    "entity_id",
)

R1_SCHEMA = "task037.extra.h2a.r1"
R1_STAGE_WORKER_SCHEMA = f"{R1_SCHEMA}.stage-worker.v1"
R1_HIT_WORKER_SCHEMA = f"{R1_SCHEMA}.hit-worker.v1"
R1_WATCHDOG_SCHEMA = f"{R1_SCHEMA}.watchdog.v1"
R1_CHECK_SCHEMA = f"{R1_SCHEMA}.check.v1"
R1_PROGRESS_SCHEMA = f"{R1_SCHEMA}.progress.v1"
R1_STAGE_TIMEOUT_SECONDS = 3600.0
R1_HIT_TIMEOUT_SECONDS = 1800.0
R1_STAGE_RSS_LIMIT_BYTES = 1_800_000_000
R1_HIT_RSS_LIMIT_BYTES = 1_750_000_000
R1_SWAP_LIMIT_BYTES = 0
R1_R0_RECORD_PATH = (
    ROOT / "benchmarks/cases/101_task37_extra_development/records"
    / "h2a_class_discovery.json"
)
R1_R0_RECORD_SHA256 = (
    "3024dea6ac33aa24c78a86e3f9ae7e699630320906134088f7df302b992e134d"
)
R1_R0_SOURCE_SHA = "b7eef17f10655be99f5bba072f9a547ae05f17ac"


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


def _proxy_ufl_forms(function_space, mesh_data, cfg):
    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    dx = ufl.Measure("dx", domain=mesh_data.mesh)
    curl_form = (
        PETSc.ScalarType(1.0 / cfg.mu_r)
        * ufl.inner(ufl.curl(u), ufl.curl(v))
        * dx
    )
    mass_form = PETSc.ScalarType(1.0) * ufl.inner(u, v) * dx
    return curl_form, mass_form


def _form_jit_options(cache_dir: Path | None = None) -> dict[str, Any]:
    jit_options: dict[str, Any] = {
        "cffi_extra_compile_args": list(H2A_FORM_JIT_EXTRA_COMPILE_ARGS),
    }
    if cache_dir is not None:
        jit_options["cache_dir"] = str(Path(cache_dir).resolve())
    return jit_options


def _proxy_forms(function_space, mesh_data, cfg, *, cache_dir: Path | None = None):
    curl_form, mass_form = _proxy_ufl_forms(function_space, mesh_data, cfg)
    jit_options = _form_jit_options(cache_dir)
    return fem.form(curl_form, jit_options=dict(jit_options)), fem.form(
        mass_form, jit_options=dict(jit_options)
    )


def _blocks_for_cell(blocks: Iterable[Any], cell_dofs: np.ndarray) -> tuple[Any, ...]:
    rows = {int(value) for value in np.asarray(cell_dofs, dtype=np.int64)}
    return tuple(
        block
        for block in blocks
        if block.slave_local_dofs
        and all(int(row) in rows for row in block.slave_local_dofs)
    )


def _discover_cell_references(
    function_space,
    mesh_data,
    cfg,
    floquet,
    *,
    geometry_tolerance: float,
    cell_order: Iterable[int] | None = None,
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
    traversal = (
        range(owned_cells)
        if cell_order is None
        else tuple(int(cell) for cell in cell_order)
    )
    if sorted(traversal) != list(range(owned_cells)):
        raise ValueError("H2A discovery cell order must cover owned cells exactly")
    for cell in traversal:
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
        "form_jit_compile_policy": {
            "cffi_extra_compile_args": list(H2A_FORM_JIT_EXTRA_COMPILE_ARGS),
        },
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
    watchdog = read_json_object(watchdog_path)
    timeline = _timeline_metrics(timeline_path)
    worker = (
        read_json_object(worker_path)
        if worker_path.is_file()
        else None
    )
    worker_present = isinstance(worker, Mapping)
    worker_eval = (
        _evaluate_h2a_worker_qualification(worker)
        if worker_present
        else {
            "schema": "task037.extra.h2a.worker.qualification.v1",
            "pass": False,
            "problems": ["worker_summary_missing"],
        }
    )
    worker_runtime = (
        worker.get("runtime_identity") if worker_present else None
    )
    watchdog_runtime = watchdog.get("runtime_identity")
    actual_timeline_artifact = {
        "path": timeline_path.name,
        "sha256": _sha256_file(timeline_path),
        "bytes": int(timeline_path.stat().st_size),
    }
    recorded_artifacts = watchdog.get("raw_artifacts")
    recorded_timeline_artifact = (
        recorded_artifacts.get("watchdog_timeline.jsonl")
        if isinstance(recorded_artifacts, Mapping)
        else None
    )
    worker_evidence_valid = (
        evidence_sha256_is_valid(worker) if worker_present else False
    )
    command = watchdog.get("command")
    watchdog_checks = {
        "schema": watchdog.get("schema") == H2A_WATCHDOG_SCHEMA,
        "status": watchdog.get("status") == "pass",
        "worker_summary_present": watchdog.get("worker_summary_present")
        is worker_present,
        "worker_evidence_valid": worker_evidence_valid,
        "watchdog_evidence_valid": evidence_sha256_is_valid(watchdog),
        "worker_qualification_pass": worker_eval["pass"],
        "watchdog_worker_qualification_pass": watchdog.get(
            "worker_qualification_pass"
        )
        is worker_eval["pass"],
        "watchdog_worker_evidence_valid": watchdog.get(
            "worker_evidence_valid"
        )
        is worker_evidence_valid,
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
            worker_present
            and watchdog.get("source_at_start")
            == worker.get("source_at_start")
            and watchdog.get("source_at_end")
            == worker.get("source_at_end")
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
        "watchdog_timeline_hash_valid": (
            isinstance(recorded_timeline_artifact, Mapping)
            and recorded_timeline_artifact.get("sha256")
            == actual_timeline_artifact["sha256"]
            and recorded_timeline_artifact.get("bytes")
            == actual_timeline_artifact["bytes"]
            and isinstance(recorded_timeline_artifact.get("path"), str)
            and Path(recorded_timeline_artifact["path"]).resolve()
            == timeline_path
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
    failure_measurements = None
    if not worker_present:
        failure_measurements = {
            "source_at_start": watchdog.get("source_at_start"),
            "source_at_end": watchdog.get("source_at_end"),
            "scope": watchdog.get("scope"),
            "runtime_identity": watchdog.get("runtime_identity"),
            "return_code": watchdog.get("return_code"),
            "termination": watchdog.get("termination"),
            "completion_elapsed_seconds": watchdog.get(
                "completion_elapsed_seconds"
            ),
            "process_tree_peak_rss_bytes": timeline["peak_rss_bytes"],
            "process_tree_swap_bytes": timeline["swap_bytes"],
            "live_sample_count": timeline["live_sample_count"],
        }
    raw_artifacts = {
        "run_summary": (
            {
                "path": worker_path.name,
                "sha256": _sha256_file(worker_path),
                "bytes": int(worker_path.stat().st_size),
            }
            if worker_present
            else {"path": worker_path.name, "present": False}
        ),
        "watchdog_summary": {
            "path": watchdog_path.name,
            "sha256": _sha256_file(watchdog_path),
            "bytes": int(watchdog_path.stat().st_size),
        },
        "watchdog_timeline": actual_timeline_artifact,
    }
    return {
        "schema": H2A_CHECK_SCHEMA,
        "status": "pass" if not problems else "gate_failed",
        "pass": not problems,
        "problems": sorted(set(problems)),
        "worker_qualification": worker_eval,
        "watchdog_checks": checks,
        "timeline": timeline,
        "measurements": measurements,
        "failure_measurements": failure_measurements,
        "raw_artifacts": raw_artifacts,
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


def _r0_scope() -> dict[str, Any]:
    return {
        **_r0_identity(),
        "mode": "class_discovery_only",
        "mpi_size": 1,
        "launch_mode": "mpi_singleton_direct",
        "cases": [
            {"label": label, "degree": degree, "h_nm": h_nm}
            for label, degree, h_nm in R0_CASES
        ],
        "timeout_seconds": R0_TIMEOUT_SECONDS,
        "rss_limit_bytes": R0_RSS_LIMIT_BYTES,
        "swap_limit_bytes": 0,
    }


def _r0_identity() -> dict[str, Any]:
    return {
        "fine_space": "uncondensed_fullspace",
        "fullspace_global_rows_h10": 173802,
        "condensation": False,
        "global_condensed_schur_materialized": False,
        "cell_schur_matrix_nnz": 0,
        "slab_matrix_nnz": 0,
        "static_condensed_operator_used": False,
        "trace_slab_pc_used": False,
        "B2_B4_local_krylov_used": False,
        "fullspace_patch_pc_used": True,
        "interior_recovery_required": False,
        "form_jit_called": False,
        "tensor_tabulation_called": False,
        "factorization_called": False,
        "global_matrix_materialized": False,
        "ordinary_default_changed": False,
        "r0_patch_or_factor_constructed": False,
    }


def _r0_worker_command(run_dir: Path, executable: str) -> list[str]:
    return [
        str(executable),
        "-m",
        "benchmarks.run_task037_extra_h2",
        "r0-worker",
        "--run-dir",
        str(run_dir.resolve()),
    ]


def _r0_emit_marker(
    stream,
    *,
    event: str,
    started: float,
    rank: int,
    case: Mapping[str, Any] | None = None,
    cell_count: int | None = None,
    global_rows: int | None = None,
    constraint_count: int | None = None,
) -> dict[str, Any]:
    marker = {
        "schema": R0_PROGRESS_SCHEMA,
        "event": str(event),
        "elapsed_wall_seconds": float(time.perf_counter() - started),
        "rank": int(rank),
        "case": None if case is None else str(case["label"]),
        "degree": None if case is None else int(case["degree"]),
        "h_nm": None if case is None else float(case["h_nm"]),
        "cell_count": None if cell_count is None else int(cell_count),
        "global_rows": None if global_rows is None else int(global_rows),
        "constraint_count": (
            None if constraint_count is None else int(constraint_count)
        ),
    }
    line = json.dumps(marker, sort_keys=True, separators=(",", ":"))
    stream.write(line + "\n")
    stream.flush()
    print(line, flush=True)
    return marker


def _r0_digest(value: Any) -> str:
    return hashlib.sha256(_key_json(value).encode("utf-8")).hexdigest()


def _r0_sha256_is_valid(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _r0_reduced_row_count(
    blocks: Iterable[Any],
    cell_local_dofs: Iterable[int],
    *,
    index_map: Any,
    index_map_bs: int,
    phase_x: complex,
    phase_y: complex,
) -> int:
    """Count reduced global rows without mixing local and global index domains."""

    if int(index_map_bs) != 1:
        raise ValueError("R0 Nedelec row mapping requires index_map_bs == 1")
    local_array = np.asarray(tuple(cell_local_dofs), dtype=np.int32)
    if local_array.ndim != 1 or local_array.size == 0:
        raise ValueError("R0 cell DoF list cannot be empty")
    global_array = np.asarray(index_map.local_to_global(local_array), dtype=np.int64)
    local_to_global = {
        int(local): int(global_row)
        for local, global_row in zip(local_array, global_array, strict=True)
    }
    independent_global_rows = set(int(value) for value in global_array)
    slave_global_rows: set[int] = set()
    master_rows: set[int] = set()
    phases = {
        "x": complex(phase_x),
        "y": complex(phase_y),
        "corner": complex(phase_x) * complex(phase_y),
    }
    for block in blocks:
        phase = phases[str(block.kind)]
        transform = np.asarray(block.coefficient_transform, dtype=np.complex128)
        for row_index, slave_local in enumerate(block.slave_local_dofs):
            slave_local = int(slave_local)
            if slave_local not in local_to_global:
                continue
            slave_global_rows.add(int(block.slave_global_dofs[row_index]))
            for column, coefficient in enumerate(transform[row_index]):
                if complex(phase * coefficient) != 0.0 + 0.0j:
                    master_rows.add(int(block.master_global_dofs[column]))
    return len((independent_global_rows - slave_global_rows) | master_rows)


def _r0_pattern_info(pattern: Iterable[Mapping[str, Any]]) -> tuple[str, list[str], int]:
    entries = tuple(pattern)
    kinds: set[str] = set()
    for entry in entries:
        topology = entry["topology"]
        topology = dict(topology) if not isinstance(topology, Mapping) else topology
        kinds.add(f"{topology['entity_kind']}:{topology['direction']}")
    return _r0_digest(entries), sorted(kinds), len(entries)


def _r0_has_forbidden_identity(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(word in lowered for word in R0_FORBIDDEN_IDENTITY_WORDS)
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(word in lowered for word in R0_FORBIDDEN_IDENTITY_WORDS):
                return True
            if _r0_has_forbidden_identity(item):
                return True
        return False
    if isinstance(value, (tuple, list)):
        return any(_r0_has_forbidden_identity(item) for item in value)
    return False


def _r0_make_class_inventory(
    function_space,
    cfg,
    floquet,
    discovery: Mapping[str, Any],
) -> dict[str, Any]:
    topology = floquet.phase_independent_topology
    if topology is None:
        raise RuntimeError("R0 discovery requires phase-independent Floquet topology")
    blocks = tuple(topology.blocks)
    index_map = function_space.dofmap.index_map
    index_map_bs = int(function_space.dofmap.index_map_bs)
    references = tuple(discovery["references"])
    representatives = discovery["representatives"]
    reduced_by_key: dict[tuple[Any, ...], set[int]] = {}
    for reference in references:
        reduced = _r0_reduced_row_count(
            _blocks_for_cell(blocks, np.asarray(reference.local_dofs, dtype=np.int64)),
            reference.local_dofs,
            index_map=index_map,
            index_map_bs=index_map_bs,
            phase_x=floquet.phase_x,
            phase_y=floquet.phase_y,
        )
        reduced_by_key.setdefault(reference.class_key, set()).add(int(reduced))
    ordered_keys = tuple(sorted(representatives, key=_key_json))
    class_inventory: list[dict[str, Any]] = []
    nloc = int(function_space.element.space_dimension)
    for class_id, key in enumerate(ordered_keys):
        reduced_values = reduced_by_key.get(key, set())
        if len(reduced_values) != 1:
            raise RuntimeError(
                "R0 cells in one exact class have inconsistent reduced-row counts"
            )
        representative = representatives[key]
        pattern = tuple(representative["pattern"])
        pattern_sha, pattern_kinds, pattern_entries = _r0_pattern_info(pattern)
        tag = int(representative["tag"])
        class_inventory.append(
            {
                "class_id": int(class_id),
                "class_key_sha256": _r0_digest(key),
                "cell_count": int(sum(ref.class_key == key for ref in references)),
                "material_tag": tag,
                "material_identity": _jsonable(_material_identity(cfg, tag)),
                "cell_widths": [float(value) for value in representative["widths"]],
                "orientation": [int(representative["cell_info"])],
                "constraint_pattern_sha256": pattern_sha,
                "constraint_pattern_kinds": pattern_kinds,
                "constraint_pattern_entry_count": int(pattern_entries),
                "local_nloc": nloc,
                "constrained_unique_reduced_row_count": int(next(iter(reduced_values))),
            }
        )
    raw_values = sum(int(item["local_nloc"]) ** 2 * 16 for item in class_inventory)
    raw_pivots = sum(int(item["local_nloc"]) * 4 for item in class_inventory)
    reduced_values = sum(
        int(item["constrained_unique_reduced_row_count"]) ** 2 * 16
        for item in class_inventory
    )
    reduced_pivots = sum(
        int(item["constrained_unique_reduced_row_count"]) * 4
        for item in class_inventory
    )
    for item in class_inventory:
        nloc_item = int(item["local_nloc"])
        reduced_item = int(item["constrained_unique_reduced_row_count"])
        item.update(
            {
                "raw_lu_values_upper_bound_bytes": nloc_item * nloc_item * 16,
                "raw_lu_pivots_upper_bound_bytes": nloc_item * 4,
                "constrained_lu_values_upper_bound_bytes": reduced_item
                * reduced_item
                * 16,
                "constrained_lu_pivots_upper_bound_bytes": reduced_item * 4,
            }
        )
    metadata_bytes = len(
        json.dumps(
            _jsonable(class_inventory), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )
    digest = _r0_digest(tuple(class_inventory))
    return {
        "class_inventory": class_inventory,
        "unique_class_count": len(class_inventory),
        "class_inventory_digest": digest,
        "forbidden_absolute_identity": _r0_has_forbidden_identity(ordered_keys),
        "metadata_bytes": int(metadata_bytes),
        "raw_lu_values_upper_bound_global_sum_bytes": int(raw_values),
        "raw_lu_pivots_upper_bound_global_sum_bytes": int(raw_pivots),
        "constrained_lu_values_upper_bound_global_sum_bytes": int(reduced_values),
        "constrained_lu_pivots_upper_bound_global_sum_bytes": int(reduced_pivots),
        "factor_upper_bound_metadata_bytes": int(metadata_bytes),
        "factor_upper_bound_raw_with_metadata_bytes": int(
            raw_values + raw_pivots + metadata_bytes
        ),
        "factor_upper_bound_constrained_with_metadata_bytes": int(
            reduced_values + reduced_pivots + metadata_bytes
        ),
        "factor_upper_bound_requires_numeric_dedup": bool(
            raw_values + raw_pivots + metadata_bytes > H2A_FACTOR_PAYLOAD_LIMIT_BYTES
            or reduced_values + reduced_pivots + metadata_bytes
            > H2A_FACTOR_PAYLOAD_LIMIT_BYTES
        ),
    }


def _r0_discover_case_inventory(
    function_space,
    mesh_data,
    cfg,
    floquet,
    *,
    geometry_tolerance: float,
) -> dict[str, Any]:
    owned_cells = int(mesh_data.mesh.topology.index_map(3).size_local)
    first = _discover_cell_references(
        function_space,
        mesh_data,
        cfg,
        floquet,
        geometry_tolerance=geometry_tolerance,
    )
    second = _discover_cell_references(
        function_space,
        mesh_data,
        cfg,
        floquet,
        geometry_tolerance=geometry_tolerance,
        cell_order=reversed(range(owned_cells)),
    )
    first_manifest = _r0_make_class_inventory(function_space, cfg, floquet, first)
    second_manifest = _r0_make_class_inventory(function_space, cfg, floquet, second)
    if first_manifest["class_inventory"] != second_manifest["class_inventory"]:
        raise RuntimeError("R0 independent class discovery manifests differ")
    if first_manifest["class_inventory_digest"] != second_manifest[
        "class_inventory_digest"
    ]:
        raise RuntimeError("R0 independent class discovery digests differ")
    return {
        **first_manifest,
        "independent_discovery_digest": second_manifest["class_inventory_digest"],
        "deterministic_discovery": True,
        "global_cell_count": int(first["global_cell_count"]),
        "references": first["references"],
    }


def _r0_run_case(
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
    mesh_data = function_space = floquet = None
    try:
        _r0_emit_marker(
            marker_stream,
            event="mesh_build_started",
            started=started,
            rank=comm.rank,
            case=case,
        )
        mesh_data = build_airbox_mesh_3d(cfg, case_dir / "mesh")
        local_cells = int(mesh_data.mesh.topology.index_map(3).size_local)
        _r0_emit_marker(
            marker_stream,
            event="mesh_build_ready",
            started=started,
            rank=comm.rank,
            case=case,
            cell_count=local_cells,
        )
        _r0_emit_marker(
            marker_stream,
            event="function_space_started",
            started=started,
            rank=comm.rank,
            case=case,
        )
        function_space = _create_nedelec_space(mesh_data.mesh, cfg)
        index_map = function_space.dofmap.index_map
        block_size = int(function_space.dofmap.index_map_bs)
        local_rows = int(index_map.size_local * block_size)
        global_rows = int(index_map.size_global * block_size)
        _r0_emit_marker(
            marker_stream,
            event="function_space_ready",
            started=started,
            rank=comm.rank,
            case=case,
            cell_count=local_cells,
            global_rows=global_rows,
        )
        _r0_emit_marker(
            marker_stream,
            event="floquet_mpc_started",
            started=started,
            rank=comm.rank,
            case=case,
            cell_count=local_cells,
            global_rows=global_rows,
        )
        floquet = build_double_floquet_mpc(function_space, mesh_data, cfg)
        constraint_count = int(floquet.num_constraints)
        _r0_emit_marker(
            marker_stream,
            event="floquet_mpc_ready",
            started=started,
            rank=comm.rank,
            case=case,
            cell_count=local_cells,
            global_rows=global_rows,
            constraint_count=constraint_count,
        )
        _r0_emit_marker(
            marker_stream,
            event="class_discovery_started",
            started=started,
            rank=comm.rank,
            case=case,
            cell_count=local_cells,
            global_rows=global_rows,
            constraint_count=constraint_count,
        )
        inventory = _r0_discover_case_inventory(
            function_space,
            mesh_data,
            cfg,
            floquet,
            geometry_tolerance=floquet_geometry_tolerance(cfg),
        )
        audit = {
            "schema": f"{R0_SCHEMA}.case-audit.v1",
            "global_cell_count": int(inventory["global_cell_count"]),
            "local_cell_count": local_cells,
            "global_rows": global_rows,
            "constraint_count": constraint_count,
            "unique_class_count": int(inventory["unique_class_count"]),
            "class_inventory": inventory["class_inventory"],
            "class_inventory_digest": inventory["class_inventory_digest"],
            "independent_discovery_digest": inventory["independent_discovery_digest"],
            "deterministic_discovery": bool(
                inventory["deterministic_discovery"]
                and inventory["class_inventory_digest"]
                == inventory["independent_discovery_digest"]
            ),
            "metadata_bytes": int(inventory["metadata_bytes"]),
            "raw_lu_values_upper_bound_global_sum_bytes": inventory[
                "raw_lu_values_upper_bound_global_sum_bytes"
            ],
            "raw_lu_pivots_upper_bound_global_sum_bytes": inventory[
                "raw_lu_pivots_upper_bound_global_sum_bytes"
            ],
            "constrained_lu_values_upper_bound_global_sum_bytes": inventory[
                "constrained_lu_values_upper_bound_global_sum_bytes"
            ],
            "constrained_lu_pivots_upper_bound_global_sum_bytes": inventory[
                "constrained_lu_pivots_upper_bound_global_sum_bytes"
            ],
            "factor_upper_bound_metadata_bytes": inventory[
                "factor_upper_bound_metadata_bytes"
            ],
            "factor_upper_bound_metadata_basis": "canonical_utf8_class_inventory",
            "factor_upper_bound_raw_with_metadata_bytes": inventory[
                "factor_upper_bound_raw_with_metadata_bytes"
            ],
            "factor_upper_bound_constrained_with_metadata_bytes": inventory[
                "factor_upper_bound_constrained_with_metadata_bytes"
            ],
            "factor_upper_bound_requires_numeric_dedup": inventory[
                "factor_upper_bound_requires_numeric_dedup"
            ],
            "identity": _r0_identity(),
            "forbidden_absolute_identity": inventory[
                "forbidden_absolute_identity"
            ],
            "factor_upper_bound_not_retained": True,
            "global_constraint_matrix_materialized": False,
            "inventory_only": True,
            "identity_fields": [
                "cell_widths",
                "material_tag",
                "material_identity",
                "orientation",
                "constraint_pattern",
                "local_dof_ordering",
                "proxy_identity",
            ],
            "constraint_pattern_semantics": (
                "normalized local topology, phase and nonzero master expansion; "
                "reported only, no C or matrix constructed"
            ),
            "finite": bool(
                all(
                    np.isfinite(float(width))
                    for item in inventory["class_inventory"]
                    for width in item["cell_widths"]
                )
            ),
        }
        result = {
            "label": label,
            "degree": int(case["degree"]),
            "h_nm": float(case["h_nm"]),
            "axis_cell_counts": [
                int(value) for value in mesh_data.mesh_cells_resolved
            ],
            "global_cell_count": int(inventory["global_cell_count"]),
            "local_cell_count": local_cells,
            "global_rows": global_rows,
            "local_rows": local_rows,
            "constraint_count": constraint_count,
            "audit": audit,
        }
        _r0_emit_marker(
            marker_stream,
            event="class_discovery_ready",
            started=started,
            rank=comm.rank,
            case=case,
            cell_count=int(inventory["global_cell_count"]),
            global_rows=global_rows,
            constraint_count=constraint_count,
        )
        return result
    finally:
        _r0_emit_marker(
            marker_stream,
            event="case_release_started",
            started=started,
            rank=comm.rank,
            case=case,
        )
        floquet = None
        function_space = None
        mesh_data = None
        clear_floquet_topology_cache()
        gc.collect()
        _r0_emit_marker(
            marker_stream,
            event="case_release_ready",
            started=started,
            rank=comm.rank,
            case=case,
        )


def _r0_run_worker(args: argparse.Namespace) -> int:
    comm = MPI.COMM_WORLD
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    progress_path = run_dir / "r0_progress.jsonl"
    summary_path = run_dir / "run_summary.json"
    source_at_start = inspect_tracked_source(ROOT)
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    error: str | None = None
    if comm.size != 1:
        error = f"R0 worker is fixed to MPI1, got {comm.size}"
    try:
        with progress_path.open("w", encoding="utf-8") as marker_stream:
            if error is None:
                for label, degree, h_nm in R0_CASES:
                    results.append(
                        _r0_run_case(
                            comm=comm,
                            case={"label": label, "degree": degree, "h_nm": h_nm},
                            run_dir=run_dir,
                            marker_stream=marker_stream,
                            started=started,
                        )
                    )
            _r0_emit_marker(
                marker_stream,
                event="worker_summary_started",
                started=started,
                rank=comm.rank,
                global_rows=(None if not results else results[0]["global_rows"]),
            )
    except (OSError, RuntimeError, ValueError, TypeError, IndexError, KeyError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    source_at_end = inspect_tracked_source(ROOT)
    payload = attach_evidence_sha256(
        {
            "schema": R0_WORKER_SCHEMA,
            "status": "measurement_complete" if error is None else "gate_failed",
            "scope": _r0_scope(),
            "source_at_start": source_at_start.as_jsonable(),
            "source_at_end": source_at_end.as_jsonable(),
            "runtime_identity": _runtime_identity(),
            "cases": results,
            "error": error,
            "inventory_only": True,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    if comm.rank == 0:
        _write_json(summary_path, payload)
    return int(comm.bcast(0 if error is None else 1, root=0))


def _r0_source_pair_is_clean(start: Any, end: Any) -> bool:
    if not isinstance(start, Mapping) or not isinstance(end, Mapping):
        return False
    for identity in (start, end):
        sha = identity.get("source_commit_full_sha")
        if (
            not isinstance(sha, str)
            or len(sha) != 40
            or sha.lower() != sha
            or any(character not in "0123456789abcdef" for character in sha)
            or identity.get("tracked_source_dirty") is not False
            or identity.get("source_worktree_dirty") is not False
            or identity.get("nonignored_untracked_paths") != []
            or identity.get("worktree_status_porcelain") != []
            or identity.get("git_error") is not None
        ):
            return False
    return start["source_commit_full_sha"] == end["source_commit_full_sha"]


def _r0_scope_is_exact(scope: Any) -> bool:
    return isinstance(scope, Mapping) and scope == _r0_scope()


def _r0_case_inventory_is_valid(case: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    audit = case.get("audit")
    if not isinstance(audit, Mapping):
        return ["audit_missing"]
    label = case.get("label")
    if audit.get("schema") != f"{R0_SCHEMA}.case-audit.v1":
        problems.append(f"{label}.audit_schema")
    expected = next((item for item in R0_CASES if item[0] == label), None)
    if expected is None or case.get("degree") != expected[1] or case.get("h_nm") != expected[2]:
        problems.append("case_identity")
    for field in ("global_cell_count", "global_rows", "constraint_count"):
        value = case.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            problems.append(f"{label}.{field}")
    if case.get("global_cell_count") != audit.get("global_cell_count"):
        problems.append(f"{label}.cell_binding")
    if case.get("global_rows") != audit.get("global_rows"):
        problems.append(f"{label}.row_binding")
    if case.get("constraint_count") != audit.get("constraint_count"):
        problems.append(f"{label}.constraint_binding")
    inventory = audit.get("class_inventory")
    count = audit.get("unique_class_count")
    if (
        not isinstance(inventory, list)
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 1
        or (label == "p6_h10" and count > 64)
        or count != len(inventory)
    ):
        problems.append(f"{label}.class_count")
        inventory = []
    if audit.get("forbidden_absolute_identity") is not False:
        problems.append(f"{label}.absolute_identity")
    expected_identity_fields = [
        "cell_widths",
        "material_tag",
        "material_identity",
        "orientation",
        "constraint_pattern",
        "local_dof_ordering",
        "proxy_identity",
    ]
    if audit.get("identity_fields") != expected_identity_fields:
        problems.append(f"{label}.identity_fields")
    computed_digest = _r0_digest(tuple(inventory))
    if audit.get("class_inventory_digest") != computed_digest:
        problems.append(f"{label}.digest")
    if audit.get("independent_discovery_digest") != computed_digest:
        problems.append(f"{label}.deterministic_digest")
    if audit.get("deterministic_discovery") is not True:
        problems.append(f"{label}.deterministic")
    if _r0_has_forbidden_identity(inventory):
        problems.append(f"{label}.manifest_identity")
    class_cell_total = 0
    raw_values = raw_pivots = reduced_values = reduced_pivots = 0
    for item in inventory:
        if not isinstance(item, Mapping):
            problems.append(f"{label}.class_item")
            continue
        class_cell_total += item.get("cell_count", 0) if isinstance(item.get("cell_count"), int) else 0
        reduced = item.get("constrained_unique_reduced_row_count")
        nloc = item.get("local_nloc")
        if (
            not isinstance(item.get("class_id"), int)
            or item["class_id"] < 0
            or not _r0_sha256_is_valid(item.get("class_key_sha256"))
            or not isinstance(item.get("cell_count"), int)
            or item["cell_count"] <= 0
            or not isinstance(nloc, int)
            or nloc <= 0
            or not isinstance(reduced, int)
            or reduced <= 0
            or not isinstance(item.get("constraint_pattern_entry_count"), int)
            or item["constraint_pattern_entry_count"] < 0
            or not _r0_sha256_is_valid(item.get("constraint_pattern_sha256"))
        ):
            problems.append(f"{label}.class_item_fields")
            continue
        if label == "p6_h10" and nloc != 882:
            problems.append(f"{label}.local_nloc")
        raw_values += nloc * nloc * 16
        raw_pivots += nloc * 4
        reduced_values += reduced * reduced * 16
        reduced_pivots += reduced * 4
        expected_item = {
            "raw_lu_values_upper_bound_bytes": nloc * nloc * 16,
            "raw_lu_pivots_upper_bound_bytes": nloc * 4,
            "constrained_lu_values_upper_bound_bytes": reduced * reduced * 16,
            "constrained_lu_pivots_upper_bound_bytes": reduced * 4,
        }
        if any(item.get(field) != value for field, value in expected_item.items()):
            problems.append(f"{label}.class_upper_bound")
    if class_cell_total != case.get("global_cell_count"):
        problems.append(f"{label}.cell_class_closure")
    if tuple(
        item.get("class_id") for item in inventory if isinstance(item, Mapping)
    ) != tuple(range(len(inventory))):
        problems.append(f"{label}.class_ids")
    upper_fields = {
        "raw_lu_values_upper_bound_global_sum_bytes": raw_values,
        "raw_lu_pivots_upper_bound_global_sum_bytes": raw_pivots,
        "constrained_lu_values_upper_bound_global_sum_bytes": reduced_values,
        "constrained_lu_pivots_upper_bound_global_sum_bytes": reduced_pivots,
    }
    for field, value in upper_fields.items():
        if audit.get(field) != value:
            problems.append(f"{label}.{field}")
    metadata = audit.get("metadata_bytes")
    if audit.get("factor_upper_bound_metadata_basis") != (
        "canonical_utf8_class_inventory"
    ):
        problems.append(f"{label}.metadata_basis")
    if not isinstance(metadata, int) or isinstance(metadata, bool) or metadata < 0:
        problems.append(f"{label}.metadata_bytes")
    else:
        recomputed_metadata = len(
            json.dumps(
                _jsonable(inventory), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        )
        if metadata != recomputed_metadata:
            problems.append(f"{label}.metadata_recomputed")
        if audit.get("factor_upper_bound_metadata_bytes") != recomputed_metadata:
            problems.append(f"{label}.metadata_upper_bound")
        raw_total = raw_values + raw_pivots + recomputed_metadata
        reduced_total = reduced_values + reduced_pivots + recomputed_metadata
        if audit.get("factor_upper_bound_raw_with_metadata_bytes") != raw_total:
            problems.append(f"{label}.raw_upper_bound")
        if audit.get("factor_upper_bound_constrained_with_metadata_bytes") != reduced_total:
            problems.append(f"{label}.reduced_upper_bound")
        if audit.get("factor_upper_bound_requires_numeric_dedup") != (
            raw_total > H2A_FACTOR_PAYLOAD_LIMIT_BYTES
            or reduced_total > H2A_FACTOR_PAYLOAD_LIMIT_BYTES
        ):
            problems.append(f"{label}.dedup_requirement")
    if audit.get("global_constraint_matrix_materialized") is not False:
        problems.append(f"{label}.global_constraint_matrix_materialized")
    if audit.get("identity") != _r0_identity():
        problems.append(f"{label}.identity")
    if audit.get("factor_upper_bound_not_retained") is not True:
        problems.append(f"{label}.factor_upper_bound_not_retained")
    if audit.get("inventory_only") is not True:
        problems.append(f"{label}.inventory_scope")
    if audit.get("finite") is not True:
        problems.append(f"{label}.finite")
    return problems


def _evaluate_r0_worker_qualification(raw: Mapping[str, Any]) -> dict[str, Any]:
    problems: list[str] = []
    if raw.get("schema") != R0_WORKER_SCHEMA:
        problems.append("schema")
    if raw.get("status") != "measurement_complete":
        problems.append("status")
    if raw.get("error") is not None:
        problems.append("error")
    if not _r0_scope_is_exact(raw.get("scope")):
        problems.append("scope")
    if raw.get("inventory_only") is not True:
        problems.append("worker_inventory_scope")
    if not _runtime_identity_is_qualified(raw.get("runtime_identity")):
        problems.append("runtime_identity")
    if not _r0_source_pair_is_clean(raw.get("source_at_start"), raw.get("source_at_end")):
        problems.append("source")
    cases = raw.get("cases")
    case_map: dict[str, Mapping[str, Any]] = {}
    if not isinstance(cases, list) or len(cases) != len(R0_CASES):
        problems.append("cases")
    else:
        for case in cases:
            if not isinstance(case, Mapping) or case.get("label") in case_map:
                problems.append("cases")
                continue
            case_map[str(case.get("label"))] = case
    for label, _degree, _h_nm in R0_CASES:
        case = case_map.get(label)
        if case is None:
            problems.append(f"missing.{label}")
        else:
            problems.extend(_r0_case_inventory_is_valid(case))
    coarse = case_map.get("p2_h10")
    refined = case_map.get("p2_h5")
    if isinstance(coarse, Mapping) and isinstance(refined, Mapping):
        coarse_cells = coarse.get("global_cell_count")
        refined_cells = refined.get("global_cell_count")
        coarse_classes = coarse.get("audit", {}).get("unique_class_count")
        refined_classes = refined.get("audit", {}).get("unique_class_count")
        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (coarse_cells, refined_cells, coarse_classes, refined_classes)
        ):
            problems.append("refinement.counts")
        elif (
            refined_cells <= coarse_cells
            or refined_classes * coarse_cells >= coarse_classes * refined_cells
        ):
            problems.append("refinement.class_growth")
    else:
        problems.append("refinement.cases")
    p6 = case_map.get("p6_h10")
    if isinstance(p6, Mapping):
        if p6.get("global_rows") != 173802:
            problems.append("p6.global_rows")
        if p6.get("constraint_count") != 9210:
            problems.append("p6.constraint_count")
    return {
        "schema": f"{R0_SCHEMA}.worker.qualification.v1",
        "pass": not problems,
        "problems": sorted(set(problems)),
    }


def _r0_timeline_metrics(path: Path) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                samples.append(json.loads(line))
    live = [sample for sample in samples if sample.get("sample_kind") == "worker"]
    readable = bool(live)
    root_pids = set()
    for sample in live:
        root = sample.get("root_pid")
        pids = sample.get("pids")
        process_count = sample.get("process_count")
        if (
            not isinstance(root, int)
            or isinstance(root, bool)
            or root <= 0
            or not isinstance(process_count, int)
            or isinstance(process_count, bool)
            or process_count < 1
            or not isinstance(pids, list)
            or len({item for item in pids if isinstance(item, int)}) != len(pids)
            or any(
                not isinstance(item, int) or isinstance(item, bool) or item <= 0
                for item in pids
            )
            or root not in pids
            or process_count != len(pids)
            or not isinstance(sample.get("rss_bytes"), int)
            or isinstance(sample.get("rss_bytes"), bool)
            or sample["rss_bytes"] < 0
            or not isinstance(sample.get("swap_bytes"), int)
            or isinstance(sample.get("swap_bytes"), bool)
            or sample["swap_bytes"] < 0
            or sample.get("all_status_readable") is not True
        ):
            readable = False
        root_pids.add(root)
    rss = [sample.get("rss_bytes") for sample in live]
    swaps = [sample.get("swap_bytes") for sample in live]
    return {
        "readable": readable and len(root_pids) == 1,
        "live_sample_count": len(live),
        "peak_rss_bytes": max(rss) if readable else None,
        "swap_bytes": max(swaps) if readable else None,
        "root_pid": next(iter(root_pids)) if len(root_pids) == 1 else None,
    }


def _r0_progress_is_valid(path: Path) -> bool:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                event = json.loads(line)
                if event.get("schema") != R0_PROGRESS_SCHEMA:
                    return False
                events.append(event)
    if not events:
        return False
    if any(
        any(word in str(event.get("event", "")).lower() for word in ("form", "tensor", "factor"))
        for event in events
    ):
        return False
    expected = (
        "mesh_build_started",
        "mesh_build_ready",
        "function_space_started",
        "function_space_ready",
        "floquet_mpc_started",
        "floquet_mpc_ready",
        "class_discovery_started",
        "class_discovery_ready",
        "case_release_started",
        "case_release_ready",
    )
    expected_sequence = [
        (label, event)
        for label, _degree, _h_nm in R0_CASES
        for event in expected
    ]
    expected_sequence.append((None, "worker_summary_started"))
    actual_sequence = [
        (event.get("case"), str(event.get("event"))) for event in events
    ]
    return actual_sequence == expected_sequence


def _r0_root_metadata_is_valid(path: Path, timeline: Mapping[str, Any]) -> bool:
    root = read_json_object(path)
    return (
        root.get("schema") == f"{R0_SCHEMA}.root.v1"
        and isinstance(root.get("root_pid"), int)
        and not isinstance(root.get("root_pid"), bool)
        and root["root_pid"] > 0
        and root["root_pid"] == timeline.get("root_pid")
    )


def _r0_actual_artifact(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "present": True,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256_file(path),
    }


def _r0_recorded_artifacts_match(
    run_dir: Path, recorded: Any, names: Iterable[str]
) -> bool:
    if not isinstance(recorded, Mapping):
        return False
    for name in names:
        path = run_dir / name
        if not path.is_file():
            return False
        item = recorded.get(name)
        if (
            not isinstance(item, Mapping)
            or item.get("path") != name
            or item.get("bytes") != path.stat().st_size
            or item.get("sha256") != _sha256_file(path)
        ):
            return False
    return True


def _r0_compact_measurements(
    worker: Mapping[str, Any], watchdog: Mapping[str, Any], timeline: Mapping[str, Any]
) -> dict[str, Any]:
    cases = {str(case["label"]): case for case in worker["cases"]}
    p6 = cases["p6_h10"]
    p2_h10 = cases["p2_h10"]
    p2_h5 = cases["p2_h5"]
    coarse_cells = p2_h10["global_cell_count"]
    refined_cells = p2_h5["global_cell_count"]
    coarse_classes = p2_h10["audit"]["unique_class_count"]
    refined_classes = p2_h5["audit"]["unique_class_count"]
    return {
        "source_commit_full_sha": worker["source_at_start"]["source_commit_full_sha"],
        "runtime_identity": worker["runtime_identity"],
        "identity": _r0_identity(),
        "raw_run_dir": watchdog["run_dir"],
        "mpi_size": 1,
        "p6_h10": {
            "degree": 6,
            "h_nm": 10.0,
            "local_nloc": p6["audit"]["class_inventory"][0]["local_nloc"],
            "global_rows": p6["global_rows"],
            "global_cells": p6["global_cell_count"],
            "constraint_count": p6["constraint_count"],
            "unique_class_count": p6["audit"]["unique_class_count"],
            "factorization_called": p6["audit"]["identity"]["factorization_called"],
            "factor_upper_bound_raw_with_metadata_bytes": p6["audit"][
                "factor_upper_bound_raw_with_metadata_bytes"
            ],
            "factor_upper_bound_constrained_with_metadata_bytes": p6["audit"][
                "factor_upper_bound_constrained_with_metadata_bytes"
            ],
            "factor_upper_bound_metadata_bytes": p6["audit"][
                "factor_upper_bound_metadata_bytes"
            ],
            "factor_upper_bound_metadata_basis": p6["audit"][
                "factor_upper_bound_metadata_basis"
            ],
            "factor_upper_bound_requires_numeric_dedup": p6["audit"][
                "factor_upper_bound_requires_numeric_dedup"
            ],
            "inventory_digest": p6["audit"]["class_inventory_digest"],
            "class_inventory": p6["audit"]["class_inventory"],
            "identity": p6["audit"]["identity"],
            "finite": p6["audit"]["finite"],
        },
        "p2_h10": {
            "global_cells": coarse_cells,
            "unique_class_count": coarse_classes,
            "inventory_digest": p2_h10["audit"]["class_inventory_digest"],
        },
        "p2_h5": {
            "global_cells": refined_cells,
            "unique_class_count": refined_classes,
            "inventory_digest": p2_h5["audit"]["class_inventory_digest"],
        },
        "refinement": {
            "coarse_cells": coarse_cells,
            "refined_cells": refined_cells,
            "coarse_classes": coarse_classes,
            "refined_classes": refined_classes,
            "class_growth_strictly_sublinear": refined_classes * coarse_cells
            < coarse_classes * refined_cells,
        },
        "process_tree": {
            "peak_rss_bytes": timeline["peak_rss_bytes"],
            "swap_bytes": timeline["swap_bytes"],
            "elapsed_wall_seconds": watchdog["completion_elapsed_seconds"],
            "termination": watchdog["termination"],
            "live_sample_count": timeline["live_sample_count"],
        },
    }


def _r0_check_raw(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    worker_path = run_dir / "run_summary.json"
    watchdog_path = run_dir / "r0_watchdog_summary.json"
    timeline_path = run_dir / "r0_watchdog_timeline.jsonl"
    progress_path = run_dir / "r0_progress.jsonl"
    root_pid_path = run_dir / "r0_root_pid.json"
    worker = read_json_object(worker_path)
    watchdog = read_json_object(watchdog_path)
    timeline = _r0_timeline_metrics(timeline_path)
    worker_valid = evidence_sha256_is_valid(worker)
    watchdog_valid = evidence_sha256_is_valid(watchdog)
    worker_eval = _evaluate_r0_worker_qualification(worker)
    source_pair = _r0_source_pair_is_clean(
        worker.get("source_at_start"), worker.get("source_at_end")
    )
    runtime = watchdog.get("runtime_identity")
    command = watchdog.get("command")
    recorded_names = (
        "r0_worker_stdout.txt",
        "r0_progress.jsonl",
        "r0_watchdog_timeline.jsonl",
        "r0_root_pid.json",
        "run_summary.json",
    )
    watchdog_checks = {
        "schema": watchdog.get("schema") == R0_WATCHDOG_SCHEMA,
        "status": watchdog.get("status") == "pass",
        "watchdog_evidence_valid": watchdog_valid,
        "worker_evidence_valid": worker_valid,
        "worker_summary_present": worker_path.is_file(),
        "worker_qualification_pass": worker_eval["pass"],
        "runtime_identity_qualified": _runtime_identity_is_qualified(runtime),
        "runtime_identity_match": (
            watchdog.get("runtime_identity") == worker.get("runtime_identity")
        ),
        "run_dir_exact": (
            isinstance(watchdog.get("run_dir"), str)
            and watchdog["run_dir"] == str(run_dir)
        ),
        "command_exact": command == _r0_worker_command(
            run_dir, runtime.get("sys_executable") if isinstance(runtime, Mapping) else ""
        ),
        "source_pair_matches": (
            watchdog.get("source_at_start") == worker.get("source_at_start")
            and watchdog.get("source_at_end") == worker.get("source_at_end")
            and source_pair
        ),
        "source_clean_flag": watchdog.get("source_clean_and_stable") is True,
        "scope_exact": watchdog.get("scope") == _r0_scope(),
        "termination_none": watchdog.get("termination") is None,
        "completion_valid": (
            isinstance(watchdog.get("completion_elapsed_seconds"), (int, float))
            and not isinstance(watchdog.get("completion_elapsed_seconds"), bool)
            and np.isfinite(watchdog["completion_elapsed_seconds"])
            and 0.0 <= watchdog["completion_elapsed_seconds"] <= R0_TIMEOUT_SECONDS
        ),
        "timeline_readable": timeline["readable"],
        "timeline_has_samples": timeline["live_sample_count"] > 0,
        "timeline_peak_strictly_below_limit": (
            isinstance(timeline["peak_rss_bytes"], int)
            and timeline["peak_rss_bytes"] < R0_RSS_LIMIT_BYTES
        ),
        "timeline_swap_zero": timeline["swap_bytes"] == 0,
        "watchdog_peak_matches_timeline": watchdog.get(
            "process_tree_peak_rss_bytes"
        ) == timeline["peak_rss_bytes"],
        "watchdog_swap_matches_timeline": watchdog.get(
            "process_tree_swap_bytes"
        ) == timeline["swap_bytes"],
        "return_code_zero": watchdog.get("return_code") == 0,
        "raw_artifacts_hash_valid": _r0_recorded_artifacts_match(
            run_dir, watchdog.get("raw_artifacts"), recorded_names
        ),
        "progress_markers_valid": _r0_progress_is_valid(progress_path),
        "root_metadata_valid": _r0_root_metadata_is_valid(root_pid_path, timeline),
    }
    problems = list(worker_eval["problems"])
    problems.extend(
        name for name, passed in watchdog_checks.items() if not passed
    )
    measurements = None
    if not problems:
        measurements = _r0_compact_measurements(worker, watchdog, timeline)
    raw_artifacts = {
        name: _r0_actual_artifact(run_dir / name) for name in recorded_names
    }
    return {
        "schema": R0_CHECK_SCHEMA,
        "status": "pass" if not problems else "gate_failed",
        "pass": not problems,
        "problems": sorted(set(problems)),
        "worker_qualification": worker_eval,
        "watchdog_checks": watchdog_checks,
        "measurements": measurements,
        "raw_artifacts": raw_artifacts,
        "raw_evidence_sha256": {
            "worker_summary_evidence_sha256": worker.get("evidence_sha256"),
            "watchdog_summary_evidence_sha256": watchdog.get("evidence_sha256"),
        },
    }


def _r0_run_watchdog(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    timeline_path = run_dir / "r0_watchdog_timeline.jsonl"
    watchdog_path = run_dir / "r0_watchdog_summary.json"
    stdout_path = run_dir / "r0_worker_stdout.txt"
    root_pid_path = run_dir / "r0_root_pid.json"
    source_at_start = inspect_tracked_source(ROOT)
    command = _r0_worker_command(run_dir, sys.executable)
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
                {"schema": f"{R0_SCHEMA}.root.v1", "root_pid": int(process.pid)},
            )
        while process is not None and process.poll() is None:
            observed = process_tree_sample(process.pid)
            sample = {
                "schema": R0_PROGRESS_SCHEMA,
                "sample_kind": "worker",
                "elapsed_wall_seconds": float(time.perf_counter() - started),
                "root_pid": int(process.pid),
                "pids": [int(pid) for pid in observed.pids],
                "process_count": len(observed.pids),
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
                termination = "swap_over_0"
            elif observed.rss_bytes >= R0_RSS_LIMIT_BYTES:
                termination = "process_tree_rss_over_1e9_bytes"
            elif sample["elapsed_wall_seconds"] >= R0_TIMEOUT_SECONDS:
                termination = "wall_timeout"
            if termination is not None:
                _h2a_terminate_process_tree(process)
                break
            time.sleep(0.25)
        if process is not None:
            return_code = process.wait()
        completion_elapsed = float(time.perf_counter() - started)
        if process is not None and termination is None and completion_elapsed > R0_TIMEOUT_SECONDS:
            termination = "wall_timeout"
        timeline_stream.write(
            json.dumps(
                {
                    "schema": R0_PROGRESS_SCHEMA,
                    "sample_kind": "final",
                    "elapsed_wall_seconds": completion_elapsed,
                    "return_code": return_code,
                },
                sort_keys=True,
            )
            + "\n"
        )
        timeline_stream.flush()
    source_at_end = inspect_tracked_source(ROOT)
    worker_path = run_dir / "run_summary.json"
    worker = read_json_object(worker_path) if worker_path.is_file() else None
    worker_valid = isinstance(worker, Mapping) and evidence_sha256_is_valid(worker)
    worker_eval = (
        _evaluate_r0_worker_qualification(worker)
        if isinstance(worker, Mapping)
        else {"pass": False, "problems": ["worker_summary_missing"]}
    )
    live_peak = max((sample["rss_bytes"] for sample in samples), default=None)
    swap = max((sample["swap_bytes"] for sample in samples), default=None)
    source_clean = _r0_source_pair_is_clean(
        source_at_start.as_jsonable(), source_at_end.as_jsonable()
    )
    raw_names = (
        "r0_worker_stdout.txt",
        "r0_progress.jsonl",
        "r0_watchdog_timeline.jsonl",
        "r0_root_pid.json",
        "run_summary.json",
    )
    raw_artifacts = {
        name: (
            {
                "path": name,
                "sha256": _sha256_file(run_dir / name),
                "bytes": int((run_dir / name).stat().st_size),
            }
            if (run_dir / name).is_file()
            else None
        )
        for name in raw_names
    }
    status = bool(
        termination is None
        and return_code == 0
        and worker_valid
        and worker_eval["pass"]
        and source_clean
        and isinstance(live_peak, int)
        and live_peak < R0_RSS_LIMIT_BYTES
        and swap == 0
    )
    payload = attach_evidence_sha256(
        {
            "schema": R0_WATCHDOG_SCHEMA,
            "status": "pass" if status else "gate_failed",
            "run_dir": str(run_dir),
            "command": command,
            "scope": _r0_scope(),
            "runtime_identity": _runtime_identity(),
            "source_at_start": source_at_start.as_jsonable(),
            "source_at_end": source_at_end.as_jsonable(),
            "source_clean_and_stable": source_clean,
            "return_code": return_code,
            "termination": termination,
            "completion_elapsed_seconds": completion_elapsed,
            "live_sample_count": len(samples),
            "process_tree_peak_rss_bytes": live_peak,
            "process_tree_swap_bytes": swap,
            "worker_summary_present": isinstance(worker, Mapping),
            "worker_evidence_valid": worker_valid,
            "worker_qualification_pass": worker_eval["pass"],
            "worker_qualification_problems": worker_eval["problems"],
            "raw_artifacts": raw_artifacts,
        }
    )
    _write_json(watchdog_path, payload)
    print(f"R0 watchdog status={payload['status']} run_dir={run_dir}", flush=True)
    return 0 if status else 1


def _r0_run_check(args: argparse.Namespace) -> int:
    try:
        result = _r0_check_raw(Path(args.run_dir))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        result = {
            "schema": R0_CHECK_SCHEMA,
            "status": "gate_failed",
            "pass": False,
            "problems": [f"raw_unreadable:{type(exc).__name__}"],
        }
    output = Path(args.output).resolve()
    _write_json(output, attach_evidence_sha256(result))
    print(f"R0 check status={result['status']} output={output}", flush=True)
    return 0 if result["pass"] else 1


def _r1_identity() -> dict[str, Any]:
    identity = dict(_r0_identity())
    for field in (
        "form_jit_called",
        "r0_patch_or_factor_constructed",
        "r1_patch_or_factor_constructed",
    ):
        identity.pop(field, None)
    return identity


def _r1_scope() -> dict[str, Any]:
    return {
        "mode": "isolated_jit_stage_and_cache_hit",
        "degree": 6,
        "h_nm": 10.0,
        "mpi_size": 1,
        "launch_mode": "mpi_singleton_direct",
        "stage_timeout_seconds": R1_STAGE_TIMEOUT_SECONDS,
        "hit_timeout_seconds": R1_HIT_TIMEOUT_SECONDS,
        "stage_rss_limit_bytes": R1_STAGE_RSS_LIMIT_BYTES,
        "hit_rss_limit_bytes": R1_HIT_RSS_LIMIT_BYTES,
        "swap_limit_bytes": R1_SWAP_LIMIT_BYTES,
        "form_jit_compile_policy": {
            "cffi_extra_compile_args": list(H2A_FORM_JIT_EXTRA_COMPILE_ARGS),
        },
        "operator": "B0=K_curl+k0^2*M_abs_epsilon",
        "identity": _r1_identity(),
    }


def _r1_worker_command(
    run_dir: Path, phase: str, executable: str
) -> list[str]:
    subcommand = {
        "stage": "r1-stage-worker",
        "hit": "r1-hit-worker",
    }.get(phase)
    if subcommand is None:
        raise ValueError(f"unknown R1 phase: {phase}")
    return [str(executable), "-m", "benchmarks.run_task037_extra_h2",
            subcommand, "--run-dir", str(run_dir.resolve())]


def _r1_emit_marker(
    stream,
    *,
    event: str,
    phase: str,
    started: float,
    rank: int = 0,
) -> dict[str, Any]:
    marker = {"schema": R1_PROGRESS_SCHEMA, "event": str(event), "phase": str(phase),
              "elapsed_wall_seconds": float(time.perf_counter() - started), "rank": int(rank)}
    line = json.dumps(marker, sort_keys=True, separators=(",", ":"))
    stream.write(line + "\n")
    stream.flush()
    print(line, flush=True)
    return marker


def _r1_compiler_probe() -> dict[str, Any]:
    compiler_setting = sysconfig.get_config_var("CC") or "cc"
    compiler_tokens = shlex.split(str(compiler_setting))
    if not compiler_tokens:
        raise ValueError("sysconfig CC is empty")
    compiler = compiler_tokens[0]
    probe_command = [compiler, "--version"]
    completed = subprocess.run(
        probe_command,
        check=True,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    version_line = next(
        (line.strip() for line in completed.stdout.splitlines() if line.strip()),
        "",
    )
    if not version_line:
        raise ValueError("compiler --version returned no text")
    return {
        "sysconfig_cc": str(compiler_setting),
        "probe_command": probe_command,
        "version_line": version_line,
    }


def _r1_runtime_identity(
    *, compiler_probe: bool = True, compiler: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    identity = {
        **_runtime_identity(),
        "python_version": platform.python_version(),
        "petsc_version": ".".join(str(value) for value in PETSc.Sys.getVersion()),
        "dolfinx_version": str(dolfinx.__version__),
        "basix_version": str(basix.__version__),
        "ffcx_version": str(ffcx.__version__),
        "ufl_version": str(ufl.__version__),
        "ffcx_header_signature": str(ffcx.codegeneration.get_signature()),
        "ufcx_header_signature": str(dolfinx.ufcx_signature),
        "sysconfig": {
            name: str(sysconfig.get_config_var(name) or "")
            for name in ("CC", "CFLAGS", "SOABI", "EXT_SUFFIX")
        },
        "compiler": _r1_compiler_probe() if compiler_probe else compiler,
    }
    if not isinstance(identity["compiler"], Mapping):
        raise ValueError("stage compiler identity is missing")
    return identity


def _r1_form_code_state(
    code: Any,
) -> tuple[str, str | None]:
    if not isinstance(code, (tuple, list)) or len(code) != 2:
        return "invalid", None
    if code[0] is None and code[1] is None:
        return "hit_no_new_decl_impl", None
    if not all(isinstance(part, str) and part for part in code):
        return "invalid", None
    code_sha256 = hashlib.sha256(
        (code[0] + "\0" + code[1]).encode("utf-8")
    ).hexdigest()
    return "cold_decl_impl_generated", code_sha256


def _r1_form_record(
    *,
    role: str,
    ufl_form: Any,
    compiled_form: Any,
    cache_dir: Path,
    cfg: Any,
    function_space: Any,
) -> dict[str, Any]:
    module_name = str(compiled_form.module.__name__)
    prefix = "libffcx_forms_"
    if not module_name.startswith(prefix):
        raise ValueError("unexpected FFCx module name")
    code_state, code_sha256 = _r1_form_code_state(compiled_form.code)
    return {
        "role": str(role),
        "ufl_signature": str(ufl_form.signature()),
        "ufcx_signature": compiled_form.module.ffi.string(
            compiled_form.ufcx_form.signature
        ).decode("ascii"),
        "module_name": module_name,
        "ffcx_signature_stem": module_name[len(prefix) :],
        "code_state": code_state,
        "code_sha256": code_sha256,
        "jit_options": _form_jit_options(cache_dir),
        "form_compiler_options": {
            "scalar_type": str(np.dtype(PETSc.ScalarType)),
        },
        "proxy_identity": _jsonable(_proxy_identity(cfg)),
        "element_signature": _jsonable(
            _canonical_basis_signature(function_space)
        ),
    }


def _r1_cache_snapshot(cache_dir: Path) -> list[dict[str, Any]]:
    if not cache_dir.is_dir():
        raise FileNotFoundError(cache_dir)
    entries = []
    for path in sorted(cache_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            raise ValueError(f"non-file cache entry: {path.name}")
        stat = path.stat()
        entries.append({"path": path.name, "bytes": int(stat.st_size),
                        "mtime_ns": int(stat.st_mtime_ns), "sha256": _sha256_file(path)})
    return entries


def _r1_cache_digest(entries: Iterable[Mapping[str, Any]]) -> str:
    data = json.dumps(_jsonable(list(entries)), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _r1_progress_events(path: Path) -> list[str]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            marker = json.loads(line)
            if marker.get("schema") != R1_PROGRESS_SCHEMA:
                raise ValueError("R1 progress schema mismatch")
            events.append(str(marker["event"]))
    return events


_R1_PROGRESS = {
    "stage": (
        "mesh_build_started", "mesh_build_ready", "function_space_started",
        "function_space_ready", "curl_form_compile_started",
        "curl_form_compile_ready", "mass_form_compile_started",
        "mass_form_compile_ready", "manifest_started", "manifest_ready",
        "worker_summary_started",
    ),
    "hit": (
        "r0_record_validation_started", "r0_record_validation_ready",
        "mesh_build_started", "mesh_build_ready", "function_space_started",
        "function_space_ready", "floquet_mpc_started", "floquet_mpc_ready",
        "curl_cache_load_started", "curl_cache_load_ready",
        "mass_cache_load_started", "mass_cache_load_ready",
        "worker_summary_started",
    ),
}


def _r1_expected_progress(phase: str) -> tuple[str, ...]:
    return _R1_PROGRESS[phase]


def _r1_read_r0_authority() -> dict[str, Any]:
    if not R1_R0_RECORD_PATH.is_file():
        raise FileNotFoundError(R1_R0_RECORD_PATH)
    record_sha256 = _sha256_file(R1_R0_RECORD_PATH)
    if record_sha256 != R1_R0_RECORD_SHA256:
        raise ValueError("R0 compact record SHA mismatch")
    record = read_json_object(R1_R0_RECORD_PATH)
    measurements = record.get("measurements")
    p6 = measurements.get("p6_h10") if isinstance(measurements, Mapping) else None
    if (
        record.get("schema") != R0_CHECK_SCHEMA
        or record.get("status") != "pass"
        or record.get("pass") is not True
        or record.get("problems") != []
        or not evidence_sha256_is_valid(record)
        or not isinstance(measurements, Mapping)
        or measurements.get("source_commit_full_sha") != R1_R0_SOURCE_SHA
        or measurements.get("mpi_size") != 1
        or not isinstance(p6, Mapping)
        or p6.get("global_rows") != H2A_FIXED_GLOBAL_ROWS
        or p6.get("constraint_count") != H2A_FIXED_CONSTRAINT_COUNT
        or p6.get("unique_class_count") != 24
        or p6.get("local_nloc") != 882
        or not isinstance(p6.get("class_inventory"), list)
        or len(p6["class_inventory"]) != 24
        or p6.get("identity") != _r0_identity()
    ):
        raise ValueError("R0 compact authority is not the frozen passing record")
    return {
        "record_sha256": record_sha256,
        "source_commit_full_sha": R1_R0_SOURCE_SHA,
        "class_count": 24,
        "local_nloc": 882,
        "global_rows": H2A_FIXED_GLOBAL_ROWS,
        "constraint_count": H2A_FIXED_CONSTRAINT_COUNT,
    }


def _r1_phase_identity(phase: str) -> dict[str, Any]:
    return {"jit_api_called": True, "compile_called": phase == "stage",
            "compiler_probe_called": phase == "stage",
            "floquet_mpc_called": phase == "hit", "class_discovery_called": False,
            "tensor_tabulation_called": False, "factorization_called": False}


def _r1_cache_files_valid(files: Any) -> bool:
    if not isinstance(files, list) or not files:
        return False
    suffixes = {".c": False, ".o": False, ".so": False, ".c.cached": False}
    paths = []
    for item in files:
        if not isinstance(item, Mapping):
            return False
        path = item.get("path")
        size, mtime, sha = item.get("bytes"), item.get("mtime_ns"), item.get("sha256")
        if not isinstance(path, str) or not path or not isinstance(size, int) or isinstance(size, bool) or size <= 0 or not isinstance(mtime, int) or isinstance(mtime, bool) or mtime <= 0 or not isinstance(sha, str) or len(sha) != 64 or sha.lower() != sha or any(char not in "0123456789abcdef" for char in sha):
            return False
        paths.append(path)
        for suffix in suffixes:
            if path.endswith(suffix):
                suffixes[suffix] = True
    return len(paths) == len(set(paths)) and all(suffixes.values())


def _r1_bind_cache_files(forms: list[dict[str, Any]], cache: list[dict[str, Any]]) -> None:
    for form in forms:
        module = str(form["module_name"])
        form["cache_files"] = [
            item for item in cache if str(item["path"]).startswith(module + ".")
        ]
        if not _r1_cache_files_valid(form["cache_files"]):
            raise ValueError(f"cache files missing for {module}")


def _r1_runtime_is_complete(identity: Any) -> bool:
    fields = (
        "python_version", "petsc_version", "dolfinx_version", "basix_version",
        "ffcx_version", "ufl_version", "ffcx_header_signature",
        "ufcx_header_signature", "sysconfig", "compiler",
    )
    return (
        _runtime_identity_is_qualified(identity)
        and isinstance(identity, Mapping)
        and all(isinstance(identity.get(field), (str, Mapping)) and identity.get(field) for field in fields)
        and isinstance(identity.get("compiler"), Mapping)
        and isinstance(identity["compiler"].get("version_line"), str)
        and bool(identity["compiler"]["version_line"])
    )


def _r1_run_worker(args: argparse.Namespace, phase: str) -> int:
    comm = MPI.COMM_WORLD
    run_dir = Path(args.run_dir).resolve()
    cache_dir = run_dir / "jit_cache"
    summary_path = run_dir / f"{phase}_summary.json"
    progress_path = run_dir / f"{phase}_progress.jsonl"
    started = time.perf_counter()
    source_at_start = inspect_tracked_source(ROOT)
    runtime: dict[str, Any] | None = None
    forms: list[dict[str, Any]] = []
    cache_before: list[dict[str, Any]] = []
    cache_after: list[dict[str, Any]] = []
    r0_authority: dict[str, Any] | None = None
    stage_manifest_sha256: str | None = None
    stage_runtime: Mapping[str, Any] | None = None
    measurement: dict[str, Any] | None = None
    error: str | None = None
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        if comm.size != 1:
            raise ValueError(f"R1 {phase} is fixed to MPI1, got {comm.size}")
        stage: Mapping[str, Any] | None = None
        if phase == "stage" and _r1_cache_snapshot(cache_dir):
            raise ValueError("R1 stage cache is not initially empty")
        with progress_path.open("w", encoding="utf-8") as markers:
            emit = lambda event: _r1_emit_marker(
                markers, event=event, phase=phase, started=started
            )
            if phase == "hit":
                emit("r0_record_validation_started")
            if phase == "hit":
                stage = read_json_object(run_dir / "stage_summary.json")
                stage_manifest_sha256 = _sha256_file(run_dir / "stage_summary.json")
                if (
                    stage.get("schema") != R1_STAGE_WORKER_SCHEMA
                    or stage.get("status") != "measurement_complete"
                    or not evidence_sha256_is_valid(stage)
                ):
                    raise ValueError("invalid stage manifest")
                r0_authority = _r1_read_r0_authority()
                stage_runtime = stage.get("runtime_identity")
                if not isinstance(stage_runtime, Mapping):
                    raise ValueError("stage runtime identity is missing")
                cache_before = _r1_cache_snapshot(cache_dir)
                if cache_before != stage.get("cache_inventory"):
                    raise ValueError("cache differs from stage manifest")
                emit("r0_record_validation_ready")
            runtime = _r1_runtime_identity(
                compiler_probe=phase == "stage",
                compiler=(stage_runtime or {}).get("compiler")
                if phase == "hit"
                else None,
            )
            cfg = target_stage4_config(degree=6, h_nm=10.0)
            emit("mesh_build_started")
            mesh_data = build_airbox_mesh_3d(cfg, run_dir / f"{phase}_mesh")
            emit("mesh_build_ready")
            emit("function_space_started")
            function_space = _create_nedelec_space(mesh_data.mesh, cfg)
            emit("function_space_ready")
            if phase == "hit":
                emit("floquet_mpc_started")
                floquet = build_double_floquet_mpc(function_space, mesh_data, cfg)
                emit("floquet_mpc_ready")
                index_map = function_space.dofmap.index_map
                measurement = {
                    "global_cells": int(mesh_data.mesh.topology.index_map(3).size_global),
                    "local_nloc": int(function_space.element.space_dimension),
                    "global_rows": int(index_map.size_global * function_space.dofmap.index_map_bs),
                    "constraint_count": int(floquet.num_constraints),
                }
                if measurement != {"global_cells": 252, "local_nloc": 882,
                                   "global_rows": H2A_FIXED_GLOBAL_ROWS,
                                   "constraint_count": H2A_FIXED_CONSTRAINT_COUNT}:
                    raise ValueError("R1 hit p6 identity mismatch")
            curl_ufl, mass_ufl = _proxy_ufl_forms(function_space, mesh_data, cfg)
            labels = ("form_compile", "form_compile") if phase == "stage" else ("cache_load", "cache_load")
            for role, form, label in zip(("curl", "mass"), (curl_ufl, mass_ufl), labels):
                emit(f"{role}_{label}_started")
                compiled = fem.form(form, jit_options=_form_jit_options(cache_dir))
                forms.append(_r1_form_record(role=role, ufl_form=form,
                                              compiled_form=compiled, cache_dir=cache_dir,
                                              cfg=cfg, function_space=function_space))
                emit(f"{role}_{label}_ready")
            cache_after = _r1_cache_snapshot(cache_dir)
            _r1_bind_cache_files(forms, cache_after)
            if phase == "hit":
                if cache_after != cache_before or not _r1_forms_match(stage.get("forms"), forms, cache_dir):
                    raise ValueError("R1 cache-hit identity mismatch")
            else:
                emit("manifest_started")
                emit("manifest_ready")
            emit("worker_summary_started")
            del mass_ufl, curl_ufl, function_space, mesh_data
            if phase == "hit":
                clear_floquet_topology_cache()
                gc.collect()
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ) as exc:
        error = f"{type(exc).__name__}: {exc}"
    source_at_end = inspect_tracked_source(ROOT)
    cache_inventory = cache_after if phase == "stage" else []
    payload = attach_evidence_sha256(
        {
            "schema": (
                R1_STAGE_WORKER_SCHEMA
                if phase == "stage"
                else R1_HIT_WORKER_SCHEMA
            ),
            "status": "measurement_complete" if error is None else "gate_failed",
            "scope": _r1_scope(),
            "phase": phase,
            "source_at_start": source_at_start.as_jsonable(),
            "source_at_end": source_at_end.as_jsonable(),
            "runtime_identity": runtime,
            "r0_authority": r0_authority,
            "initial_cache_empty": phase == "stage" and not cache_before,
            "stage_manifest_sha256": stage_manifest_sha256,
            "forms": forms,
            "cache_inventory": cache_inventory,
            "cache_inventory_sha256": _r1_cache_digest(cache_inventory),
            "cache_before": cache_before if phase == "hit" else None,
            "cache_after": cache_after if phase == "hit" else None,
            "cache_unchanged": (
                cache_before == cache_after if phase == "hit" else None
            ),
            "measurement": measurement,
            "identity": _r1_identity(),
            "phase_identity": _r1_phase_identity(phase),
            "error": error,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    _write_json(summary_path, payload)
    return 0 if error is None else 1


def _r1_run_stage_worker(args: argparse.Namespace) -> int:
    return _r1_run_worker(args, "stage")


def _r1_run_hit_worker(args: argparse.Namespace) -> int:
    return _r1_run_worker(args, "hit")


def _r1_last_progress_event(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            if line.strip():
                return str(json.loads(line)["event"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return None


def _r1_compiler_descendant_pids(
    pids: Iterable[int], root_pid: int
) -> list[int]:
    compiler_pids = []
    for pid in pids:
        if int(pid) == int(root_pid):
            continue
        try:
            name = Path(Path(f"/proc/{int(pid)}/cmdline").read_bytes().split(b"\0", 1)[0].decode("utf-8", errors="replace")).name
        except OSError:
            continue
        if (
            "gcc" in name
            or name in {"cc", "cc1", "cc1plus", "collect2", "clang", "clang++"}
        ):
            compiler_pids.append(int(pid))
    return sorted(set(compiler_pids))


def _r1_run_phase(
    *,
    run_dir: Path,
    phase: str,
    controller_started: float,
    timeout_seconds: float,
    rss_limit_bytes: int,
) -> dict[str, Any]:
    progress_path = run_dir / f"{phase}_progress.jsonl"
    command = _r1_worker_command(run_dir, phase, sys.executable)
    phase_started = time.perf_counter()
    process: subprocess.Popen[Any] | None = None
    termination: str | None = None
    samples: list[dict[str, Any]] = []
    try:
        with (run_dir / f"{phase}_stdout.txt").open("w", encoding="utf-8") as stdout, (run_dir / f"{phase}_timeline.jsonl").open("w", encoding="utf-8") as timeline:
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=subprocess.STDOUT, start_new_session=True)
            while process.poll() is None:
                try:
                    observed = process_tree_sample(process.pid)
                except (OSError, ValueError):
                    termination = "authority_unreadable"
                    _h2a_terminate_process_tree(process)
                    break
                elapsed = float(time.perf_counter() - phase_started)
                sample = {
                    "schema": R1_PROGRESS_SCHEMA, "sample_kind": "worker", "phase": phase,
                    "elapsed_wall_seconds": elapsed, "root_pid": int(process.pid),
                    "pids": [int(pid) for pid in observed.pids], "process_count": len(observed.pids),
                    "rss_bytes": int(observed.rss_bytes), "swap_bytes": int(observed.swap_bytes),
                    "all_status_readable": bool(observed.all_status_readable),
                    "progress_event": _r1_last_progress_event(progress_path),
                    "compiler_descendant_pids": _r1_compiler_descendant_pids(observed.pids, process.pid),
                }
                samples.append(sample)
                timeline.write(json.dumps(sample, sort_keys=True, separators=(",", ":")) + "\n")
                timeline.flush()
                if not observed.all_status_readable:
                    termination = "authority_unreadable"
                elif observed.swap_bytes > R1_SWAP_LIMIT_BYTES:
                    termination = "swap_nonzero"
                elif observed.rss_bytes >= rss_limit_bytes:
                    termination = f"process_tree_rss_over_{rss_limit_bytes}_bytes"
                elif elapsed >= timeout_seconds:
                    termination = "wall_timeout"
                if termination is not None:
                    _h2a_terminate_process_tree(process)
                    break
                time.sleep(0.05)
            return_code = process.wait()
            completion_elapsed = float(time.perf_counter() - phase_started)
            if termination is None and completion_elapsed > timeout_seconds:
                termination = "wall_timeout_post_exit"
            timeline.write(json.dumps({"schema": R1_PROGRESS_SCHEMA, "sample_kind": "final", "phase": phase, "elapsed_wall_seconds": completion_elapsed, "return_code": return_code}, sort_keys=True, separators=(",", ":")) + "\n")
            timeline.flush()
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        if process is not None and process.poll() is None:
            _h2a_terminate_process_tree(process)
            process.wait()
        raise
    all_pids = sorted({int(pid) for sample in samples for pid in sample["pids"] if int(pid) != int(process.pid)})
    compiler_pids = sorted({int(pid) for sample in samples for pid in sample["compiler_descendant_pids"]})
    return {
        "phase": phase,
        "command": command,
        "root_pid": int(process.pid),
        "return_code": int(return_code),
        "termination": termination,
        "completion_elapsed_seconds": completion_elapsed,
        "controller_elapsed_start": float(phase_started - controller_started),
        "controller_elapsed_end": float(time.perf_counter() - controller_started),
        "live_sample_count": len(samples),
        "process_tree_peak_rss_bytes": (
            max((sample["rss_bytes"] for sample in samples), default=None)
        ),
        "process_tree_swap_bytes": (
            max((sample["swap_bytes"] for sample in samples), default=None)
        ),
        "observed_process_tree_pids": all_pids,
        "observed_compiler_descendant_pids": compiler_pids,
    }


def _r1_artifact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": path.name, "present": False}
    return {"path": path.name, "present": True, "bytes": int(path.stat().st_size), "sha256": _sha256_file(path)}


def _r1_timeline_metrics(path: Path, phase: str) -> dict[str, Any]:
    samples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            sample = json.loads(line)
            if sample.get("schema") != R1_PROGRESS_SCHEMA or sample.get("phase") != phase:
                raise ValueError("R1 timeline schema or phase mismatch")
            samples.append(sample)
    live = [sample for sample in samples if sample.get("sample_kind") == "worker"]
    if not live:
        return {
            "readable": False, "live_sample_count": 0, "peak_rss_bytes": None,
            "swap_bytes": None, "compiler_descendant_pids": [],
            "compile_marker_samples": 0,
            "compile_marker_compiler_descendant_count": None,
            "cache_load_samples": 0, "cache_load_compiler_descendant_count": None,
        }
    readable = all(
        isinstance(sample.get("rss_bytes"), int)
        and not isinstance(sample["rss_bytes"], bool)
        and sample["rss_bytes"] >= 0
        and isinstance(sample.get("swap_bytes"), int)
        and not isinstance(sample["swap_bytes"], bool)
        and sample["swap_bytes"] >= 0
        and sample.get("all_status_readable") is True
        and isinstance(sample.get("pids"), list)
        and all(isinstance(pid, int) and not isinstance(pid, bool) and pid > 0 for pid in sample["pids"])
        and isinstance(sample.get("process_count"), int)
        and sample["process_count"] >= 0
        and sample["process_count"] == len(sample["pids"])
        and isinstance(sample.get("compiler_descendant_pids"), list)
        and all(isinstance(pid, int) and not isinstance(pid, bool) and pid > 0 for pid in sample["compiler_descendant_pids"])
        for sample in live
    )
    compiler_pids = sorted({int(pid) for sample in live for pid in sample["compiler_descendant_pids"]})
    cache_events = {"curl_cache_load_started", "curl_cache_load_ready", "mass_cache_load_started", "mass_cache_load_ready"}
    compile_events = {"curl_form_compile_started", "curl_form_compile_ready", "mass_form_compile_started", "mass_form_compile_ready"}
    cache_samples = [s for s in live if phase == "hit" and s.get("progress_event") in cache_events]
    compile_samples = [s for s in live if phase == "stage" and s.get("progress_event") in compile_events]
    def max_children(items):
        return max((len(s["compiler_descendant_pids"]) for s in items), default=None)
    return {
        "readable": readable, "live_sample_count": len(live),
        "peak_rss_bytes": max(s["rss_bytes"] for s in live),
        "swap_bytes": max(s["swap_bytes"] for s in live),
        "compiler_descendant_pids": compiler_pids,
        "compile_marker_samples": len(compile_samples),
        "compile_marker_compiler_descendant_count": max_children(compile_samples),
        "cache_load_samples": len(cache_samples),
        "cache_load_compiler_descendant_count": max_children(cache_samples),
    }


def _r1_run_watchdog(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    if run_dir.exists():
        raise FileExistsError(f"R1 run directory already exists: {run_dir}")
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir()
    controller_started, source_at_start = time.perf_counter(), inspect_tracked_source(ROOT)
    runtime_identity: dict[str, Any] | None = None
    stage: dict[str, Any] | None = None
    hit: dict[str, Any] | None = None
    error: str | None = None
    try:
        stage = _r1_run_phase(run_dir=run_dir, phase="stage", controller_started=controller_started, timeout_seconds=R1_STAGE_TIMEOUT_SECONDS, rss_limit_bytes=R1_STAGE_RSS_LIMIT_BYTES)
        pids = {int(stage["root_pid"]), *map(int, stage["observed_process_tree_pids"])}
        stage["processes_gone_before_hit"] = all(not Path(f"/proc/{pid}").exists() for pid in pids)
        stage_path = run_dir / "stage_summary.json"
        stage_ok = stage["return_code"] == 0 and stage["termination"] is None and stage["processes_gone_before_hit"] and stage_path.is_file()
        if stage_ok:
            summary = read_json_object(stage_path)
            runtime_identity = summary.get("runtime_identity")
            stage_ok = (
                summary.get("status") == "measurement_complete"
                and evidence_sha256_is_valid(summary)
                and _r1_runtime_is_complete(runtime_identity)
            )
        if stage_ok:
            hit = _r1_run_phase(run_dir=run_dir, phase="hit", controller_started=controller_started, timeout_seconds=R1_HIT_TIMEOUT_SECONDS, rss_limit_bytes=R1_HIT_RSS_LIMIT_BYTES)
        else:
            error = "stage_gate_failed_before_hit"
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ) as exc:
        error = f"{type(exc).__name__}: {exc}"
    source_at_end = inspect_tracked_source(ROOT)
    if stage is not None:
        stage["hit_started_after_stage_exit"] = bool(hit and hit["controller_elapsed_start"] > stage["controller_elapsed_end"])
    summaries = [
        {"source_at_start": source_at_start.as_jsonable(), "source_at_end": source_at_end.as_jsonable()},
        *[read_json_object(run_dir / name) for name in ("stage_summary.json", "hit_summary.json") if (run_dir / name).is_file()],
    ]
    shas = []
    source_clean = True
    for item in summaries:
        start, end = item.get("source_at_start"), item.get("source_at_end")
        source_clean = source_clean and _r0_source_pair_is_clean(start, end)
        if isinstance(start, Mapping) and isinstance(end, Mapping):
            shas += [start["source_commit_full_sha"], end["source_commit_full_sha"]]
    source_clean = source_clean and bool(shas) and len(set(shas)) == 1
    status = bool(error is None and stage and hit and stage["return_code"] == hit["return_code"] == 0 and stage["termination"] is None and hit["termination"] is None and stage.get("processes_gone_before_hit") and stage.get("hit_started_after_stage_exit") and source_clean and runtime_identity)
    raw_artifact_names = ("stage_progress.jsonl", "stage_stdout.txt", "stage_summary.json", "stage_timeline.jsonl", "hit_progress.jsonl", "hit_stdout.txt", "hit_summary.json", "hit_timeline.jsonl")
    payload = attach_evidence_sha256(
        {
            "schema": R1_WATCHDOG_SCHEMA,
            "status": "pass" if status else "gate_failed",
            "run_dir": str(run_dir),
            "scope": _r1_scope(),
            "runtime_identity": runtime_identity,
            "source_at_start": source_at_start.as_jsonable(),
            "source_at_end": source_at_end.as_jsonable(),
            "source_clean_and_stable": source_clean,
            "stage": stage,
            "hit": hit,
            "error": error,
            "completion_elapsed_seconds": float(time.perf_counter() - controller_started),
            "raw_artifacts": {
                name: _r1_artifact(run_dir / name)
                for name in raw_artifact_names
            },
        }
    )
    _write_json(run_dir / "r1_watchdog_summary.json", payload)
    print(f"R1 watchdog status={payload['status']} run_dir={run_dir}", flush=True)
    return 0 if status else 1


def _r1_forms_match(
    stage_forms: Any, hit_forms: Any, expected_cache_dir: Path
) -> bool:
    if not isinstance(stage_forms, list) or not isinstance(hit_forms, list) or len(stage_forms) != 2 or len(hit_forms) != 2:
        return False
    required = {"role", "ufl_signature", "ufcx_signature", "module_name", "ffcx_signature_stem", "jit_options", "form_compiler_options", "proxy_identity", "element_signature", "cache_files", "code_state", "code_sha256"}
    if [item.get("role") for item in stage_forms if isinstance(item, Mapping)] != ["curl", "mass"] or [item.get("role") for item in hit_forms if isinstance(item, Mapping)] != ["curl", "mass"]:
        return False
    modules = [item.get("module_name") for item in stage_forms if isinstance(item, Mapping)]
    if len(modules) != 2 or len(set(modules)) != 2:
        return False
    for stage_form, hit_form in zip(stage_forms, hit_forms):
        if not isinstance(stage_form, Mapping) or not isinstance(hit_form, Mapping) or not required.issubset(stage_form) or not required.issubset(hit_form):
            return False
        if stage_form["module_name"] != "libffcx_forms_" + stage_form["ffcx_signature_stem"]:
            return False
        if any(not isinstance(stage_form[key], str) or not stage_form[key] for key in ("ufl_signature", "ufcx_signature", "module_name", "ffcx_signature_stem")):
            return False
        if (
            stage_form["jit_options"] != _form_jit_options(expected_cache_dir)
            or stage_form["form_compiler_options"] != {"scalar_type": "complex128"}
            or not isinstance(stage_form["proxy_identity"], (Mapping, list, tuple))
            or not stage_form["proxy_identity"]
            or not isinstance(stage_form["element_signature"], (Mapping, list, tuple))
            or not stage_form["element_signature"]
        ):
            return False
        code_sha = stage_form["code_sha256"]
        if stage_form["code_state"] != "cold_decl_impl_generated" or not isinstance(code_sha, str) or len(code_sha) != 64 or code_sha.lower() != code_sha or any(char not in "0123456789abcdef" for char in code_sha) or hit_form["code_state"] != "hit_no_new_decl_impl" or hit_form["code_sha256"] is not None:
            return False
        if not _r1_cache_files_valid(stage_form["cache_files"]) or stage_form["cache_files"] != hit_form["cache_files"]:
            return False
        if any(
            not str(item["path"]).startswith(stage_form["module_name"] + ".")
            for item in stage_form["cache_files"]
        ):
            return False
        if any(hit_form[key] != stage_form[key] for key in required - {"code_state", "code_sha256"}):
            return False
    return True


def _r1_check_raw(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    stage_path, hit_path = run_dir / "stage_summary.json", run_dir / "hit_summary.json"
    watchdog = read_json_object(run_dir / "r1_watchdog_summary.json")
    stage, hit, runtime = read_json_object(stage_path), read_json_object(hit_path), None
    r0_authority = _r1_read_r0_authority()
    runtime = watchdog.get("runtime_identity")
    stage_progress = _r1_progress_events(run_dir / "stage_progress.jsonl")
    hit_progress = _r1_progress_events(run_dir / "hit_progress.jsonl")
    stage_timeline = _r1_timeline_metrics(run_dir / "stage_timeline.jsonl", "stage")
    hit_timeline = _r1_timeline_metrics(run_dir / "hit_timeline.jsonl", "hit")
    stage_phase, hit_phase = watchdog.get("stage"), watchdog.get("hit")
    pairs = ({"source_at_start": watchdog.get("source_at_start"), "source_at_end": watchdog.get("source_at_end")}, stage, hit)
    shas: list[str] = []
    source_ok = True
    for pair in pairs:
        start = pair.get("source_at_start") if isinstance(pair, Mapping) else None
        end = pair.get("source_at_end") if isinstance(pair, Mapping) else None
        source_ok = _r0_source_pair_is_clean(start, end) and source_ok
        if isinstance(start, Mapping) and isinstance(end, Mapping):
            shas += [str(start["source_commit_full_sha"]), str(end["source_commit_full_sha"])]
    source_ok = source_ok and bool(shas) and len(set(shas)) == 1

    def identity_ok(summary: Any, phase: str) -> bool:
        return (isinstance(summary, Mapping)
                and summary.get("schema") == (R1_STAGE_WORKER_SCHEMA if phase == "stage" else R1_HIT_WORKER_SCHEMA)
                and summary.get("status") == "measurement_complete" and summary.get("error") is None
                and summary.get("scope") == _r1_scope() and summary.get("identity") == _r1_identity()
                and summary.get("phase_identity") == _r1_phase_identity(phase)
                and _r1_runtime_is_complete(summary.get("runtime_identity"))
                and evidence_sha256_is_valid(summary)
                )

    def time_ok(phase: Any, limit: float) -> bool:
        value = phase.get("completion_elapsed_seconds") if isinstance(phase, Mapping) else None
        return isinstance(value, (int, float)) and not isinstance(value, bool) and np.isfinite(value) and 0.0 <= value <= limit

    def cache_binding_closed(forms: Any, inventory: Any) -> bool:
        if not isinstance(forms, list) or not isinstance(inventory, list):
            return False
        bound = [item for form in forms if isinstance(form, Mapping) for item in form.get("cache_files", [])]
        return len(bound) == len(inventory) and sorted(bound, key=lambda item: item.get("path", "")) == sorted(inventory, key=lambda item: item.get("path", ""))

    phase_specs = ((stage_phase, stage_timeline, "stage", R1_STAGE_TIMEOUT_SECONDS), (hit_phase, hit_timeline, "hit", R1_HIT_TIMEOUT_SECONDS))
    phase_ok = all(
        isinstance(phase, Mapping) and phase.get("return_code") == 0 and phase.get("termination") is None
        and time_ok(phase, limit) and timeline["readable"] and isinstance(timeline["peak_rss_bytes"], int)
        and timeline["peak_rss_bytes"] < (R1_STAGE_RSS_LIMIT_BYTES if name == "stage" else R1_HIT_RSS_LIMIT_BYTES)
        and timeline["swap_bytes"] == 0 and phase.get("process_tree_peak_rss_bytes") == timeline["peak_rss_bytes"]
        and phase.get("process_tree_swap_bytes") == timeline["swap_bytes"]
        for phase, timeline, name, limit in phase_specs
    )
    artifact_names = ("stage_progress.jsonl", "stage_stdout.txt", "stage_summary.json", "stage_timeline.jsonl", "hit_progress.jsonl", "hit_stdout.txt", "hit_summary.json", "hit_timeline.jsonl")
    recorded = watchdog.get("raw_artifacts")
    artifacts_ok = isinstance(recorded, Mapping) and all(
        isinstance(recorded.get(name), Mapping) and recorded[name] == _r1_artifact(run_dir / name) and recorded[name].get("present") is True
        for name in artifact_names
    )
    checks = {
        "schema": watchdog.get("schema") == R1_WATCHDOG_SCHEMA,
        "status": watchdog.get("status") == "pass",
        "watchdog_evidence_valid": evidence_sha256_is_valid(watchdog),
        "run_dir_exact": watchdog.get("run_dir") == str(run_dir),
        "scope_exact": watchdog.get("scope") == _r1_scope(),
        "runtime_complete": _r1_runtime_is_complete(runtime),
        "source_clean_and_stable": source_ok,
        "worker_identity": stage.get("runtime_identity") == runtime and hit.get("runtime_identity") == runtime,
        "stage_identity": identity_ok(stage, "stage"), "hit_identity": identity_ok(hit, "hit"),
        "progress_exact": tuple(stage_progress) == _r1_expected_progress("stage") and tuple(hit_progress) == _r1_expected_progress("hit"),
        "phase_resources": phase_ok,
        "stage_compiler": bool(stage_timeline["compiler_descendant_pids"]) and stage_timeline["compile_marker_samples"] > 0 and stage_timeline["compile_marker_compiler_descendant_count"] > 0,
        "hit_cache_load": not hit_timeline["compiler_descendant_pids"],
        "phase_order": isinstance(stage_phase, Mapping) and isinstance(hit_phase, Mapping) and stage_phase.get("processes_gone_before_hit") is True and stage_phase.get("hit_started_after_stage_exit") is True and hit_phase.get("controller_elapsed_start", -1) > stage_phase.get("controller_elapsed_end", float("inf")),
        "commands": isinstance(runtime, Mapping) and isinstance(stage_phase, Mapping) and isinstance(hit_phase, Mapping) and stage_phase.get("command") == _r1_worker_command(run_dir, "stage", str(runtime.get("sys_executable"))) and hit_phase.get("command") == _r1_worker_command(run_dir, "hit", str(runtime.get("sys_executable"))),
        "r0_authority": hit.get("r0_authority") == r0_authority,
        "stage_manifest_sha_exact": hit.get("stage_manifest_sha256") == _sha256_file(stage_path),
        "hit_measurement": hit.get("measurement") == {"global_cells": 252, "local_nloc": 882, "global_rows": H2A_FIXED_GLOBAL_ROWS, "constraint_count": H2A_FIXED_CONSTRAINT_COUNT},
        "forms": _r1_forms_match(stage.get("forms"), hit.get("forms"), run_dir / "jit_cache"),
        "cache": stage.get("initial_cache_empty") is True and isinstance(stage.get("cache_inventory"), list) and stage.get("cache_inventory_sha256") == _r1_cache_digest(stage["cache_inventory"]) and hit.get("cache_unchanged") is True and hit.get("cache_before") == hit.get("cache_after") == stage.get("cache_inventory") and _r1_cache_snapshot(run_dir / "jit_cache") == stage.get("cache_inventory"),
        "cache_binding_closed": cache_binding_closed(stage.get("forms"), stage.get("cache_inventory")) and cache_binding_closed(hit.get("forms"), hit.get("cache_after")),
        "raw_artifacts_hash_valid": artifacts_ok,
        "watchdog_completion_valid": time_ok(watchdog, float("inf")),
    }
    problems = sorted(
        name for name, passed in checks.items() if passed is not True
    )
    measurements = None
    if not problems:
        measurements = {
            "source_commit_full_sha": runtime and watchdog[
                "source_at_start"
            ]["source_commit_full_sha"],
            "runtime_identity": runtime,
            "r0_authority": r0_authority,
            "stage": {
                "forms": stage["forms"],
                "cache_inventory": stage["cache_inventory"],
                "completion_elapsed_seconds": stage_phase["completion_elapsed_seconds"],
                "process_tree_peak_rss_bytes": stage_timeline["peak_rss_bytes"],
                "swap_bytes": stage_timeline["swap_bytes"],
                "compiler_descendant_pids": stage_timeline[
                    "compiler_descendant_pids"
                ],
                "compiler_descendant_count": len(stage_timeline["compiler_descendant_pids"]),
                "processes_gone_before_hit": stage_phase["processes_gone_before_hit"],
            },
            "hit": {
                "measurement": hit["measurement"],
                "forms": hit["forms"],
                "completion_elapsed_seconds": hit_phase["completion_elapsed_seconds"],
                "process_tree_peak_rss_bytes": hit_timeline["peak_rss_bytes"],
                "swap_bytes": hit_timeline["swap_bytes"],
                "compiler_child_process_count": len(hit_timeline["compiler_descendant_pids"]),
                "form_jit_cache_hit": True,
                "c_source_regeneration": False,
                "cache_inventory_unchanged": hit["cache_unchanged"],
                "cache_load_compiler_descendant_count": hit_timeline[
                    "cache_load_compiler_descendant_count"
                ],
            },
            "identity": _r1_identity(),
        }
    return {
        "schema": R1_CHECK_SCHEMA,
        "status": "pass" if not problems else "gate_failed",
        "pass": not problems,
        "problems": problems,
        "watchdog_checks": checks,
        "stage_timeline": stage_timeline,
        "hit_timeline": hit_timeline,
        "measurements": measurements,
        "raw_artifacts": {
            name: _r1_artifact(run_dir / name)
            for name in (
                "stage_progress.jsonl",
                "stage_stdout.txt",
                "stage_summary.json",
                "stage_timeline.jsonl",
                "hit_progress.jsonl",
                "hit_stdout.txt",
                "hit_summary.json",
                "hit_timeline.jsonl",
                "r1_watchdog_summary.json",
            )
        },
    }


def _r1_run_check(args: argparse.Namespace) -> int:
    try:
        result = _r1_check_raw(Path(args.run_dir))
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        result = {
            "schema": R1_CHECK_SCHEMA,
            "status": "gate_failed",
            "pass": False,
            "problems": [f"raw_unreadable:{type(exc).__name__}"],
        }
    output = Path(args.output).resolve()
    _write_json(output, attach_evidence_sha256(result))
    print(f"R1 check status={result['status']} output={output}", flush=True)
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
    r0_worker = sub.add_parser("r0-worker")
    r0_worker.add_argument("--run-dir", required=True)
    r0_worker.set_defaults(handler=_r0_run_worker)
    r0_watchdog = sub.add_parser("r0-watchdog")
    r0_watchdog.add_argument("--run-dir", required=True)
    r0_watchdog.set_defaults(handler=_r0_run_watchdog)
    r0_checker = sub.add_parser("r0-check")
    r0_checker.add_argument("--run-dir", required=True)
    r0_checker.add_argument("--output", required=True)
    r0_checker.set_defaults(handler=_r0_run_check)
    r1_stage_worker = sub.add_parser("r1-stage-worker")
    r1_stage_worker.add_argument("--run-dir", required=True)
    r1_stage_worker.set_defaults(handler=_r1_run_stage_worker)
    r1_hit_worker = sub.add_parser("r1-hit-worker")
    r1_hit_worker.add_argument("--run-dir", required=True)
    r1_hit_worker.set_defaults(handler=_r1_run_hit_worker)
    r1_watchdog = sub.add_parser("r1-watchdog")
    r1_watchdog.add_argument("--run-dir", required=True)
    r1_watchdog.set_defaults(handler=_r1_run_watchdog)
    r1_checker = sub.add_parser("r1-check")
    r1_checker.add_argument("--run-dir", required=True)
    r1_checker.add_argument("--output", required=True)
    r1_checker.set_defaults(handler=_r1_run_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
