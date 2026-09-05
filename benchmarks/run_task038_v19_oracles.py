"""Thin Review V19 R0 orchestration for the PML double-sweep prototype.

R0 builds only structure inventories and the one approved p2/MPI1 fixture.  It
does not run an outer Krylov solve.  The reusable PML maps and local meshes
live in :mod:`src.solvers.fullspace_pml_double_sweep`; this module only binds
the input identity, small evidence record, and fail-closed root lifecycle.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np

from src.solvers.fullspace_pml_double_sweep import (
    PML_SWEEP_PROFILE,
    SWEEP_ORDER,
    build_structure_inventory,
    build_z_quartile_plan,
    count_unique_structural_pairs,
    materialize_dolfinx_pml_quartile_plan,
    mpc_global_row_replacements,
    pml_profile_facts,
)


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_v19_oracles"
PHASE = "r0"
P6_SYMBOLIC_PHASE = "r0-p6-symbolic"
PROFILE = PML_SWEEP_PROFILE
MPI_SIZE = 1
P2_DEGREE = 2
P6_DEGREE = 6
PML_LAYER_COUNT = 2
R0_SCHEMA = "task038.v19.r0.record.v1"
P6_SYMBOLIC_PARENT_SCHEMA = "task038.v19.r0.p6-slab1-mumps-symbolic.parent.v1"
P6_SYMBOLIC_WORKER_SCHEMA = "task038.v19.r0.p6-slab1-mumps-symbolic.worker.v1"
P2_MUMPS_HARD_BYTES = 2_000_000_000
P6_MUMPS_WARNING_BYTES = 10_000_000_000
P6_MUMPS_HARD_BYTES = 12_000_000_000
P6_REFERENCE_INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
P6_SLAB1_STRUCTURAL_ENTRIES = 136_361_232
P6_RESOURCE_STOP_REASONS = frozenset(
    {"process_tree_rss_watchdog", "process_tree_swap"}
)
P6_SOURCE_FILES = (
    Path("benchmarks/run_task038_v19_oracles.py"),
    Path("src/solvers/fullspace_pml_double_sweep.py"),
    Path("src/solvers/fullspace_v17_p3_oracle.py"),
    Path("src/solvers/fullspace_same_mesh_hcurl_pmg_setup.py"),
)
MARKER_ORDER = (
    "paths_ready",
    "abi_ready",
    "p2_fixture_complete",
    "p6_inventory_complete",
    "record_written",
    "release_complete",
)
P6_SYMBOLIC_PARENT_MARKER_ORDER = (
    "paths_ready",
    "abi_ready",
    "worker_complete",
    "record_written",
    "release_complete",
)
P6_SYMBOLIC_WORKER_MARKER_ORDER = (
    "paths_ready",
    "abi_ready",
    "p6_levels_built",
    "p6_plan_built",
    "slab1_local_mesh_built",
    "local_form_compiled",
    "local_aij_assembled",
    "symbolic_complete",
    "record_written",
    "release_complete",
)
REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while block := stream.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"cannot encode {type(value).__name__}")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(_jsonable(value), stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()


def _write_marker(marker_dir: Path, name: str, facts: dict[str, Any]) -> None:
    index = MARKER_ORDER.index(name)
    path = marker_dir / f"{index:02d}_{name}.json"
    _write_json(path, {"schema": "task038.v19.r0.marker.v1", "name": name, **facts})


def _write_ordered_marker(
    marker_dir: Path,
    name: str,
    facts: dict[str, Any],
    order: tuple[str, ...],
    schema: str,
) -> None:
    index = order.index(name)
    _write_json(
        marker_dir / f"{index:02d}_{name}.json",
        {"schema": schema, "name": name, **facts},
    )


def _cell_rows_and_layers(space: Any, z_values: np.ndarray) -> tuple[list[np.ndarray], list[int]]:
    from dolfinx import mesh

    mesh_object = space.mesh
    tdim = mesh_object.topology.dim
    count = int(mesh_object.topology.index_map(tdim).size_local)
    midpoints = mesh.compute_midpoints(
        mesh_object, tdim, np.arange(count, dtype=np.int32)
    )
    rows: list[np.ndarray] = []
    layers: list[int] = []
    for cell, midpoint in enumerate(midpoints):
        dofs = np.asarray(space.dofmap.cell_dofs(cell), dtype=np.int32)
        rows.append(
            np.asarray(
                space.dofmap.index_map.local_to_global(dofs), dtype=np.int64
            )
        )
        layer = int(np.searchsorted(z_values, midpoint[2], side="right") - 1)
        layers.append(max(0, min(layer, len(z_values) - 2)))
    return rows, layers


def _layer_rows(cell_rows: list[np.ndarray], layers: list[int], layer_count: int) -> tuple[np.ndarray, ...]:
    grouped: list[list[np.ndarray]] = [[] for _ in range(layer_count)]
    for rows, layer in zip(cell_rows, layers, strict=True):
        grouped[int(layer)].append(rows)
    return tuple(
        np.unique(np.concatenate(items)).astype(np.int64)
        for items in grouped
    )


def _destroy_mpc_bundle(levels: dict[str, Any]) -> None:
    for floquet in levels.get("floquets", {}).values():
        mpc = getattr(floquet, "mpc", None)
        if mpc is not None:
            del mpc._cpp_object


def _p2_mumps_memory_preflight(analysis_facts: dict[str, Any]) -> dict[str, Any]:
    """Build the measured p2 MUMPS prediction used by the diagnostic solve."""

    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot

    snapshot = process_tree_snapshot(os.getpid(), "r0_p2_mumps_post_analysis")
    live_rss = snapshot.get("rss_bytes")
    infog = analysis_facts.get("raw_info", {}).get("infog", {})
    infog16 = infog.get("16") if isinstance(infog, dict) else None
    if type(live_rss) is not int or live_rss < 0:
        raise RuntimeError("p2 MUMPS post-analysis process-tree RSS is unreadable")
    if type(infog16) is not int:
        raise RuntimeError("p2 MUMPS INFOG(16) is unreadable")
    predicted = live_rss + max(int(infog16), 0) * 1_000_000
    return {
        "formula": "post_analysis_process_tree_rss_bytes + max(INFOG(16), 0) * 1000000",
        "post_analysis_process_tree_rss_bytes": int(live_rss),
        "post_analysis_process_tree_swap_bytes": snapshot.get("swap_bytes"),
        "post_analysis_process_tree_pss_bytes": snapshot.get("pss_bytes"),
        "post_analysis_all_status_readable": snapshot.get("all_status_readable"),
        "infog16": int(infog16),
        "predicted_peak_bytes": int(predicted),
        "hard_limit_bytes": P2_MUMPS_HARD_BYTES,
        "safe_cap": "R0 p2 local diagnostic hard cap",
    }


def _p2_fixture(cfg: Any, comm: Any) -> dict[str, Any]:
    """Build one real p2 local PML mesh and record only compact facts."""

    from dolfinx import fem, mesh
    import dolfinx_mpc
    import ufl
    from petsc4py import PETSc

    from src.solvers.fullspace_pml_double_sweep import (
        build_local_pml_physical_action,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from src.geometry.mesh_builder_3d import stage4_axis_plan
    from src.solvers.fullspace_v17_p3_oracle import (
        analyze_mumps_p3,
        solve_mumps_p3,
    )

    p2_cfg = replace(cfg, nedelec_degree=P2_DEGREE, visualization_degree=P2_DEGREE)
    levels = _build_same_mesh_levels(
        p2_cfg, comm, (P2_DEGREE,), include_positive_coefficients=False
    )
    materialized = None
    action = None
    matrix = None
    source = None
    expected = None
    observed = None
    observed_first = None
    difference = None
    repeat_difference = None
    mumps_residual = None
    mumps_solution = None
    factor = None
    stretch_one_action = None
    stretch_one_matrix = None
    stretch_one_expected = None
    stretch_one_observed = None
    stretch_one_difference = None
    zero_boundary_value = None
    reference_matrix = None
    reference_expected = None
    reference_difference = None
    try:
        axes = stage4_axis_plan(p2_cfg, comm.size)
        space = levels["spaces"][P2_DEGREE]
        floquet = levels["floquets"][P2_DEGREE]
        cell_rows, layers = _cell_rows_and_layers(space, axes.z_values)
        rows_by_layer = _layer_rows(cell_rows, layers, len(axes.z_values) - 1)
        plan = build_z_quartile_plan(axes.z_values, rows_by_layer)
        materialized = materialize_dolfinx_pml_quartile_plan(
            plan,
            space,
            floquet,
            levels["mesh_data"],
            axes.x_values,
            axes.y_values,
            cfg=p2_cfg,
            degree=P2_DEGREE,
            comm=comm,
        )
        # Both artificial ends are present on this fixed interior slab.  The
        # other three slabs are still included in the map/PoU inventory.
        local = materialized.subdomains[1]
        local_space = local.local_space
        local_floquet = local.local_floquet
        local_mesh = local.local_mesh
        z_min = float(np.min(local_mesh.geometry.x[:, 2]))
        z_max = float(np.max(local_mesh.geometry.x[:, 2]))
        boundary_facets = mesh.locate_entities_boundary(
            local_mesh,
            local_mesh.topology.dim - 1,
            lambda x: np.isclose(x[2], z_min) | np.isclose(x[2], z_max),
        )
        boundary_rows = fem.locate_dofs_topological(
            local_space,
            local_mesh.topology.dim - 1,
            boundary_facets,
        )
        zero_boundary_value = fem.Function(local_space)
        zero_boundary = fem.dirichletbc(zero_boundary_value, boundary_rows)
        form, action, form_facts = build_local_pml_physical_action(
            local,
            p2_cfg,
            boundary_rows,
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        compiled = fem.form(form, jit_options=dict(SAME_MESH_JIT_OPTIONS))
        matrix = dolfinx_mpc.assemble_matrix(
            compiled, local_floquet.mpc, bcs=[zero_boundary]
        )
        matrix.assemble()
        source = matrix.createVecRight()
        source_values = source.getArray()
        source_values[:] = 1.0 + 0.01 * np.arange(source_values.size) + 0.2j
        boundary_rows = np.unique(np.asarray(boundary_rows, dtype=np.int32))
        boundary_rows = boundary_rows[boundary_rows < source_values.size]
        if boundary_rows.size:
            source_values[boundary_rows] = 0.0
        owned_slaves = np.asarray(local_floquet.mpc.slaves, dtype=np.int32)
        owned_slaves = owned_slaves[owned_slaves < source_values.size]
        if owned_slaves.size:
            source_values[owned_slaves] = 0.0
        source_before = sha256(
            memoryview(np.ascontiguousarray(source_values)).cast("B")
        ).hexdigest()
        expected = matrix.createVecLeft()
        observed = matrix.createVecLeft()
        observed_first = matrix.createVecLeft()
        matrix.mult(source, expected)
        action.matrix.mult(source, observed)
        observed.copy(result=observed_first)
        expected_values = np.asarray(expected.getArray(readonly=True))
        observed_values = np.asarray(observed.getArray(readonly=True))
        difference = observed.copy()
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        relative = float(difference.norm() / max(expected.norm(), 1.0e-30))
        action.matrix.mult(source, observed)
        repeat_difference = observed.copy()
        repeat_difference.axpy(PETSc.ScalarType(-1.0), observed_first)
        repeat_relative = float(
            repeat_difference.norm() / max(observed_first.norm(), 1.0e-30)
        )
        source_after = sha256(
            memoryview(
                np.ascontiguousarray(source.getArray(readonly=True))
            ).cast("B")
        ).hexdigest()
        factor, analysis_facts = analyze_mumps_p3(matrix)
        memory_preflight = _p2_mumps_memory_preflight(analysis_facts)
        mumps_solution, solve_facts = solve_mumps_p3(
            factor,
            matrix,
            source,
            predicted_peak_bytes=memory_preflight["predicted_peak_bytes"],
            hard_limit_bytes=memory_preflight["hard_limit_bytes"],
        )
        if mumps_solution is None:
            raise RuntimeError("p2 MUMPS memory preflight blocked the local solve")
        mumps_residual = matrix.createVecLeft()
        matrix.mult(mumps_solution, mumps_residual)
        mumps_residual.axpy(PETSc.ScalarType(-1.0), source)
        mumps_relative = float(
            mumps_residual.norm() / max(source.norm(), 1.0e-30)
        )
        stretch_one_form, stretch_one_action, _stretch_one_facts = (
            build_local_pml_physical_action(
                local,
                p2_cfg,
                boundary_rows,
                jit_options=SAME_MESH_JIT_OPTIONS,
                stretch_override=1.0,
            )
        )
        stretch_one_compiled = fem.form(
            stretch_one_form,
            jit_options=dict(SAME_MESH_JIT_OPTIONS),
        )
        stretch_one_matrix = dolfinx_mpc.assemble_matrix(
            stretch_one_compiled,
            local_floquet.mpc,
            bcs=[zero_boundary],
        )
        stretch_one_matrix.assemble()
        stretch_one_expected = stretch_one_matrix.createVecLeft()
        stretch_one_observed = stretch_one_matrix.createVecLeft()
        stretch_one_matrix.mult(source, stretch_one_expected)
        stretch_one_action.matrix.mult(source, stretch_one_observed)
        stretch_one_difference = stretch_one_observed.copy()
        stretch_one_difference.axpy(
            PETSc.ScalarType(-1.0), stretch_one_expected
        )
        stretch_one_relative = float(
            stretch_one_difference.norm()
            / max(stretch_one_expected.norm(), 1.0e-30)
        )
        # Independent unstretched reference: assemble the original Maxwell
        # weak form directly over the copied material tags, without calling
        # the PML form builder.
        reference_u = ufl.TrialFunction(local_space)
        reference_v = ufl.TestFunction(local_space)
        reference_dx = ufl.Measure(
            "dx",
            domain=local_mesh,
            subdomain_data=local.local_mesh_data.cell_tags,
        )
        reference_curl_u = ufl.curl(reference_u)
        reference_curl_v = ufl.curl(reference_v)
        reference_form = 0
        reference_materials = {
            int(p2_cfg.tags.air): (complex(p2_cfg.eps_r), complex(p2_cfg.mu_r)),
            int(p2_cfg.tags.substrate): (
                complex(p2_cfg.substrate_index**2),
                complex(p2_cfg.mu_r),
            ),
            int(p2_cfg.tags.grating): (
                complex(p2_cfg.grating_index**2),
                complex(p2_cfg.mu_r),
            ),
        }
        for tag, (epsilon, permeability) in reference_materials.items():
            reference_form += (
                (1.0 / permeability)
                * ufl.inner(reference_curl_u, reference_curl_v)
                - p2_cfg.k0**2
                * epsilon
                * ufl.inner(reference_u, reference_v)
            ) * reference_dx(tag)
        reference_compiled = fem.form(
            reference_form,
            jit_options=dict(SAME_MESH_JIT_OPTIONS),
        )
        reference_matrix = dolfinx_mpc.assemble_matrix(
            reference_compiled,
            local_floquet.mpc,
            bcs=[zero_boundary],
        )
        reference_matrix.assemble()
        reference_expected = reference_matrix.createVecLeft()
        reference_matrix.mult(source, reference_expected)
        reference_difference = reference_expected.copy()
        reference_difference.axpy(
            PETSc.ScalarType(-1.0),
            stretch_one_observed,
        )
        original_maxwell_relative = float(
            reference_difference.norm()
            / max(stretch_one_observed.norm(), 1.0e-30)
        )
        pairing_global_dual = (
            0.75 + 0.01 * np.arange(
                int(space.dofmap.index_map.size_global), dtype=np.float64
            ) + 0.13j
        )
        pairing_local_primal = (
            0.25 + 0.02 * np.arange(
                int(local.physical_map.local_size), dtype=np.float64
            ) - 0.07j
        )
        pairing_left = np.vdot(
            local.physical_map.restrict_dual(pairing_global_dual),
            pairing_local_primal,
        )
        pairing_right = np.vdot(
            pairing_global_dual,
            local.physical_map.prolong_primal(
                pairing_local_primal,
                int(space.dofmap.index_map.size_global),
            ),
        )
        pairing_relative = float(
            abs(pairing_left - pairing_right)
            / max(abs(pairing_right), np.finfo(np.float64).tiny)
        )
        map_input = 1.0 + 0.01 * np.arange(
            int(space.dofmap.index_map.size_global), dtype=np.float64
        ) + 0.05j
        map_input_sha = sha256(
            memoryview(np.ascontiguousarray(map_input)).cast("B")
        ).hexdigest()
        map_dual = local.physical_map.restrict_dual(map_input)
        map_roundtrip = local.physical_map.prolong_primal(
            map_dual,
            int(space.dofmap.index_map.size_global),
        )
        mapped_rows = local.physical_map.global_rows
        map_relative = float(
            np.linalg.norm(map_roundtrip[mapped_rows] - map_input[mapped_rows])
            / max(
                np.linalg.norm(map_input[mapped_rows]),
                np.finfo(np.float64).tiny,
            )
        )
        map_input_after_sha = sha256(
            memoryview(np.ascontiguousarray(map_input)).cast("B")
        ).hexdigest()
        local_pml_profile = {
            side: pml_profile_facts(
                float(local.pml_thicknesses_nm[side])
            )
            for side in local.pml_sides
        }
        map_audit = local.physical_map.audit()
        map_audit["local_position_count"] = len(map_audit.pop("local_positions"))
        map_audit["local_positions_sha256"] = sha256(
            np.ascontiguousarray(local.physical_map.local_positions).view(np.uint8)
        ).hexdigest()
        facts = {
            "degree": P2_DEGREE,
            "global_space_rows": int(space.dofmap.index_map.size_global),
            "local_subdomain": int(local.subdomain_id),
            "pml_rows_materialized": materialized.audit["pml_rows_materialized"],
            "pml_local_mesh_facts": materialized.audit["pml_local_mesh_facts"],
            "map_audit": map_audit,
            "pou_max_error": float(materialized.audit["pou_max_error"]),
            "local_action_relative": relative,
            "local_action_repeat_relative": repeat_relative,
            "stretch_one_local_maxwell_relative": stretch_one_relative,
            "stretch_one_original_maxwell_relative": original_maxwell_relative,
            "map_dual_primal_relative": map_relative,
            "map_hermitian_pairing_relative": pairing_relative,
            "map_input_unchanged": map_input_sha == map_input_after_sha,
            "pml_outgoing_profile": local_pml_profile,
            "input_unchanged": source_before == source_after,
            "source_finite": bool(np.all(np.isfinite(source_values))),
            "output_finite": bool(
                np.all(np.isfinite(expected_values))
                and np.all(np.isfinite(observed_values))
            ),
            "finite": bool(
                np.isfinite(relative)
                and np.isfinite(repeat_relative)
                and np.all(np.isfinite(source_values))
                and np.all(np.isfinite(expected_values))
                and np.all(np.isfinite(observed_values))
            ),
            "owned_slave_count": int(owned_slaves.size),
            "owned_slave_max": float(
                np.max(np.abs(source_values[owned_slaves]))
                if owned_slaves.size
                else 0.0
            ),
            "form_facts": form_facts,
            "jit_options": dict(SAME_MESH_JIT_OPTIONS),
            "mumps": {
                "analysis": analysis_facts,
                "resource_preflight": memory_preflight,
                "solve": solve_facts,
                "explicit_residual_relative": mumps_relative,
                "finite": bool(np.isfinite(mumps_relative)),
            },
        }
        factor.destroy()
        facts["mumps"]["release"] = {
            "factor_destroyed": bool(factor.destroyed),
            "same_factor_symbolic_numeric_solve": True,
        }
        return facts
    finally:
        for value in (
            mumps_residual,
            mumps_solution,
            difference,
            repeat_difference,
            observed_first,
            observed,
            expected,
            source,
            stretch_one_difference,
            stretch_one_observed,
            stretch_one_expected,
            reference_difference,
            reference_expected,
        ):
            destroy = getattr(value, "destroy", None)
            if callable(destroy):
                destroy()
        if factor is not None:
            factor.destroy()
        for value in (
            stretch_one_action,
            stretch_one_matrix,
            action,
            matrix,
            reference_matrix,
        ):
            destroy = getattr(value, "destroy", None)
            if callable(destroy):
                destroy()
        if materialized is not None:
            from src.solvers.fullspace_pml_double_sweep import destroy_materialized_pml_quartile_plan

            destroy_materialized_pml_quartile_plan(materialized)
        _destroy_mpc_bundle(levels)


def _p6_inventory(cfg: Any, comm: Any) -> dict[str, Any]:
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.geometry.mesh_builder_3d import stage4_axis_plan

    levels = _build_same_mesh_levels(
        cfg, comm, (P6_DEGREE,), include_positive_coefficients=False
    )
    try:
        axes = stage4_axis_plan(cfg, comm.size)
        space = levels["spaces"][P6_DEGREE]
        floquet = levels["floquets"][P6_DEGREE]
        cell_rows, layers = _cell_rows_and_layers(space, axes.z_values)
        replacements = mpc_global_row_replacements(space, floquet)
        structure = build_structure_inventory(
            axes.z_values,
            cell_rows,
            layers,
            row_replacements=replacements,
        )
        plan = build_z_quartile_plan(
            axes.z_values,
            _layer_rows(cell_rows, layers, len(axes.z_values) - 1),
        )
        trace_rows = [
            np.intersect1d(
                plan.subdomains[index].core_global_rows,
                plan.subdomains[index + 1].core_global_rows,
            )
            for index in range(len(plan.subdomains) - 1)
        ]
        slave_rows = set(int(row) for row in replacements)
        trace_non_slave_counts = [
            int(sum(int(row) not in slave_rows for row in rows))
            for rows in trace_rows
        ]
        trace_master_counts = [
            int(
                len(
                    {
                        master
                        for row in rows
                        for master in replacements.get(int(row), (int(row),))
                    }
                )
            )
            for rows in trace_rows
        ]
        plan.audit["interface_trace_non_slave_row_counts"] = trace_non_slave_counts
        plan.audit["interface_trace_independent_master_counts"] = trace_master_counts
        materialized = materialize_dolfinx_pml_quartile_plan(
            plan,
            space,
            floquet,
            levels["mesh_data"],
            axes.x_values,
            axes.y_values,
            cfg=cfg,
            degree=P6_DEGREE,
            comm=comm,
        )
        local_facts = []
        for item in materialized.subdomains:
            z_local = np.asarray(
                materialized.audit["pml_local_mesh_facts"][item.subdomain_id][
                    "z_values_nm"
                ],
                dtype=np.float64,
            )
            local_rows, local_layers = _cell_rows_and_layers(
                item.local_space, z_local
            )
            local_replacements = mpc_global_row_replacements(
                item.local_space, item.local_floquet
            )
            local_pairs = count_unique_structural_pairs(
                local_rows,
                int(item.local_space.dofmap.index_map.size_global),
                row_replacements=local_replacements,
            )
            local_facts.append(
                {
                    "subdomain_id": int(item.subdomain_id),
                    "physical_rows": int(item.physical_map.global_rows.size),
                    "pml_rows": int(item.pml_local_row_count),
                    "local_space_global_rows": int(item.local_space.dofmap.index_map.size_global),
                    "local_cell_count": len(local_rows),
                    "local_layer_count": len(set(local_layers)),
                    "local_structural_pairs": int(local_pairs),
                }
            )
        return {
            "degree": P6_DEGREE,
            "space_global_rows": int(space.dofmap.index_map.size_global),
            "space_local_rows": int(space.dofmap.index_map.size_local),
            "global_structure": structure,
            "pml_audit": materialized.audit,
            "local_facts": local_facts,
            "numeric_allgather": False,
            "matrix_assembled": False,
        }
    finally:
        if "materialized" in locals():
            from src.solvers.fullspace_pml_double_sweep import destroy_materialized_pml_quartile_plan

            destroy_materialized_pml_quartile_plan(materialized)
        _destroy_mpc_bundle(levels)


def _p6_symbolic_source_facts(source_sha: str, input_path: Path) -> dict[str, Any]:
    if len(source_sha) != 40 or any(char not in "0123456789abcdef" for char in source_sha):
        raise ValueError("source SHA must be a complete lowercase Git SHA")
    input_path = Path(os.path.abspath(os.fspath(input_path)))
    input_sha = _sha256_file(input_path)
    if input_sha != P6_REFERENCE_INPUT_SHA256:
        raise RuntimeError("p6 symbolic preflight requires the frozen reference input")
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "--git-dir=.git-codex", "--work-tree=.", *args],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "Git source identity probe failed")
        return result.stdout.strip()

    branch = git("branch", "--show-current")
    head = git("rev-parse", "HEAD")
    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    upstream_sha = git("rev-parse", "@{upstream}")
    counts = git("rev-list", "--left-right", "--count", "HEAD...@{upstream}").split()
    status = git("status", "--porcelain", "--untracked-files=all")
    if branch != BRANCH or upstream != f"origin/{BRANCH}" or counts != ["0", "0"]:
        raise RuntimeError("p6 symbolic source branch/upstream is not the Task038 branch")
    if head != source_sha:
        raise RuntimeError("checkout HEAD does not match the p6 symbolic source SHA")
    source_files = {
        path.as_posix(): _sha256_file(REPO_ROOT / path)
        for path in P6_SOURCE_FILES
    }
    return {
        "source_sha": source_sha,
        "input_relative_path": str(input_path.relative_to(REPO_ROOT)),
        "input_sha256": input_sha,
        "git": {
            "branch": branch,
            "head": head,
            "upstream": upstream,
            "upstream_sha": upstream_sha,
            "ahead": int(counts[0]),
            "behind": int(counts[1]),
            "worktree_dirty": bool(status),
            "status_porcelain": status.splitlines(),
            "source_sha_matches_head": head == source_sha,
        },
        "source_files": source_files,
    }


def _p6_symbolic_launch_budget() -> dict[str, Any]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, _, rest = line.partition(":")
        if key in {"MemTotal", "MemAvailable"}:
            values[key] = int(rest.strip().split()[0]) * 1024
    mem_total = values.get("MemTotal")
    mem_available = values.get("MemAvailable")
    if type(mem_total) is not int or type(mem_available) is not int:
        raise RuntimeError("/proc/meminfo does not expose MemTotal and MemAvailable")
    reserve = max(4 * 1024**3, int(0.1 * mem_total))
    cap = min(P6_MUMPS_HARD_BYTES, mem_available - reserve)
    if cap <= 0:
        raise RuntimeError("p6 symbolic launch budget is non-positive")
    value_bytes = P6_SLAB1_STRUCTURAL_ENTRIES * np.dtype(np.complex128).itemsize
    index_bytes = P6_SLAB1_STRUCTURAL_ENTRIES * np.dtype(np.int32).itemsize
    return {
        "formula": "min(12000000000, MemAvailable - max(4GiB, 0.1*MemTotal))",
        "mem_total_bytes": mem_total,
        "mem_available_bytes": mem_available,
        "reserve_bytes": reserve,
        "launch_cap_bytes": int(cap),
        "warning_bytes": P6_MUMPS_WARNING_BYTES,
        "hard_limit_bytes": P6_MUMPS_HARD_BYTES,
        "watchdog_scope": [
            "compiler_descendants",
            "local_AIJ_assembly",
            "MUMPS_conversion",
            "MUMPS_symbolic",
        ],
        "numeric_and_solve_forbidden": True,
        "swap_required": 0,
        "known_slab1_preassembly_estimate": {
            "structural_entries": P6_SLAB1_STRUCTURAL_ENTRIES,
            "source": "prior measured V19 p6/h10 slab1 structural inventory",
            "storage": "complex128 values (16 B) plus int32 indices (4 B)",
            "aij_value_bytes": value_bytes,
            "aij_index_bytes": index_bytes,
            "mumps_conversion_value_bytes": value_bytes,
            "mumps_conversion_row_index_bytes": index_bytes,
            "mumps_conversion_column_index_bytes": index_bytes,
            "simultaneous_known_bytes": 2 * value_bytes + 3 * index_bytes,
            "unmodeled": [
                "PETSc row-pointer and allocator overhead",
                "MUMPS internal conversion/symbolic workspace beyond these arrays",
            ],
            "sufficiency_claim": False,
        },
    }


def _p6_symbolic_worker_command(
    root: Path, record_path: Path, source_sha: str, input_path: Path
) -> list[str]:
    return [
        "mpiexec",
        "-n",
        "1",
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        "-m",
        MODULE,
        "--phase",
        P6_SYMBOLIC_PHASE,
        "--mode",
        "worker",
        "--artifact-root",
        str(root),
        "--record",
        str(record_path),
        "--source-sha",
        source_sha,
        "--input",
        str(input_path),
        "--mpi-size",
        "1",
    ]


def _p6_symbolic_worker(
    root: Path,
    record_path: Path,
    source_sha: str,
    input_path: Path,
    expected_size: int,
) -> int:
    root = Path(os.path.abspath(os.fspath(root)))
    record_path = Path(os.path.abspath(os.fspath(record_path)))
    jit_cache = root / "jit_cache"
    if not root.is_dir() or not jit_cache.is_dir():
        raise FileNotFoundError("p6 symbolic worker requires root/jit_cache")
    os.environ["XDG_CACHE_HOME"] = str(jit_cache)
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    from dolfinx import fem, mesh
    import dolfinx_mpc
    from mpi4py import MPI
    from petsc4py import PETSc

    from src.geometry.mesh_builder_3d import stage4_axis_plan
    from src.io.input_validation import load_and_resolve, simulation_config_3d_from_normalized
    from src.solvers.fullspace_pml_double_sweep import (
        build_local_pml_physical_form,
        destroy_materialized_pml_quartile_plan,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from src.solvers.fullspace_v17_p3_oracle import analyze_mumps_p3

    comm = MPI.COMM_WORLD
    if int(comm.size) != int(expected_size):
        raise RuntimeError(f"p6 symbolic MPI size mismatch: {comm.size} != {expected_size}")
    if int(comm.rank) == 0:
        worker_marker_dir = root / "raw" / "worker_markers"
        worker_marker_dir.mkdir(exist_ok=False)
        _write_ordered_marker(
            worker_marker_dir,
            "paths_ready",
            {"source_sha": source_sha},
            P6_SYMBOLIC_WORKER_MARKER_ORDER,
            "task038.v19.r0.p6-slab1-mumps-symbolic.marker.v1",
        )
    comm.barrier()
    worker_marker_dir = root / "raw" / "worker_markers"

    specification = load_and_resolve(input_path)
    if specification.input_sha256 != P6_REFERENCE_INPUT_SHA256:
        raise RuntimeError("p6 symbolic worker input identity mismatch")
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    p6_cfg = replace(
        cfg,
        nedelec_degree=P6_DEGREE,
        visualization_degree=P6_DEGREE,
    )
    abi = {
        "qualified_activation": os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION"),
        "python": sys.executable,
        "python_prefix": sys.prefix,
        "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
        "petsc_int_type": str(np.dtype(PETSc.IntType)),
        "mpi_size": int(comm.size),
        "threads": {
            name: os.environ.get(name, "1")
            for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        },
        "jit_cache_binding": {
            "xdg_cache_home": str(jit_cache),
            "ffcx_cache_root": str(jit_cache / "fenics"),
        },
    }
    if (
        abi["qualified_activation"] != "1"
        or abi["petsc_scalar_type"] != "complex128"
        or abi["petsc_int_type"] != "int32"
        or any(value != "1" for value in abi["threads"].values())
    ):
        raise RuntimeError("qualified p6 symbolic ABI preflight failed")
    if int(comm.rank) == 0:
        _write_ordered_marker(
            worker_marker_dir,
            "abi_ready",
            abi,
            P6_SYMBOLIC_WORKER_MARKER_ORDER,
            "task038.v19.r0.p6-slab1-mumps-symbolic.marker.v1",
        )

    levels = _build_same_mesh_levels(
        p6_cfg, comm, (P6_DEGREE,), include_positive_coefficients=False
    )
    materialized = None
    matrix = None
    factor = None
    factor_destroyed = False
    try:
        if int(comm.rank) == 0:
            _write_ordered_marker(
                worker_marker_dir,
                "p6_levels_built",
                {
                    "degree": P6_DEGREE,
                    "include_positive_coefficients": False,
                },
                P6_SYMBOLIC_WORKER_MARKER_ORDER,
                "task038.v19.r0.p6-slab1-mumps-symbolic.marker.v1",
            )
        axes = stage4_axis_plan(p6_cfg, comm.size)
        space = levels["spaces"][P6_DEGREE]
        floquet = levels["floquets"][P6_DEGREE]
        cell_rows, layers = _cell_rows_and_layers(space, axes.z_values)
        plan = build_z_quartile_plan(
            axes.z_values,
            _layer_rows(cell_rows, layers, len(axes.z_values) - 1),
        )
        replacements = mpc_global_row_replacements(space, floquet)
        trace_rows = [
            np.intersect1d(
                plan.subdomains[index].core_global_rows,
                plan.subdomains[index + 1].core_global_rows,
            )
            for index in range(len(plan.subdomains) - 1)
        ]
        if int(comm.rank) == 0:
            _write_ordered_marker(
                worker_marker_dir,
                "p6_plan_built",
                {
                    "cell_count": len(cell_rows),
                    "layer_count": len(axes.z_values) - 1,
                    "space_global_rows": int(space.dofmap.index_map.size_global),
                    "mpc_row_replacements": len(replacements),
                    "interface_trace_row_counts": [int(rows.size) for rows in trace_rows],
                    "interface_trace_independent_master_counts": [
                        int(
                            len(
                                {
                                    master
                                    for row in rows
                                    for master in replacements.get(int(row), (int(row),))
                                }
                            )
                        )
                        for rows in trace_rows
                    ],
                },
                P6_SYMBOLIC_WORKER_MARKER_ORDER,
                "task038.v19.r0.p6-slab1-mumps-symbolic.marker.v1",
            )
        materialized = materialize_dolfinx_pml_quartile_plan(
            plan,
            space,
            floquet,
            levels["mesh_data"],
            axes.x_values,
            axes.y_values,
            cfg=p6_cfg,
            degree=P6_DEGREE,
            comm=comm,
        )
        local = materialized.subdomains[1]
        local_mesh = local.local_mesh
        local_space = local.local_space
        z_min = float(np.min(local_mesh.geometry.x[:, 2]))
        z_max = float(np.max(local_mesh.geometry.x[:, 2]))
        boundary_facets = mesh.locate_entities_boundary(
            local_mesh,
            local_mesh.topology.dim - 1,
            lambda x: np.isclose(x[2], z_min) | np.isclose(x[2], z_max),
        )
        boundary_rows = fem.locate_dofs_topological(
            local_space,
            local_mesh.topology.dim - 1,
            boundary_facets,
        )
        zero_boundary_value = fem.Function(local_space)
        zero_boundary = fem.dirichletbc(zero_boundary_value, boundary_rows)
        if int(comm.rank) == 0:
            local_facts = materialized.audit["pml_local_mesh_facts"][1]
            _write_ordered_marker(
                worker_marker_dir,
                "slab1_local_mesh_built",
                {
                    "materialized_subdomain": 1,
                    "boundary_row_count": int(np.asarray(boundary_rows).size),
                    "cell_count": int(
                        local_facts["physical_cell_count"] + local_facts["pml_cell_count"]
                    ),
                    "storage_rows": int(local_facts["local_space_raw_owned_rows"]),
                    "independent_rows": int(local_facts["local_space_independent_rows"]),
                    "physical_rows": int(local_facts["physical_global_row_count"]),
                    "pml_rows": int(local_facts["pml_only_local_row_count"]),
                },
                P6_SYMBOLIC_WORKER_MARKER_ORDER,
                "task038.v19.r0.p6-slab1-mumps-symbolic.marker.v1",
            )
        pre_assembly_snapshot = process_tree_snapshot(
            os.getpid(), "r0_p6_before_local_aij"
        )
        form, form_facts = build_local_pml_physical_form(local, p6_cfg)
        compiled = fem.form(form, jit_options=dict(SAME_MESH_JIT_OPTIONS))
        if int(comm.rank) == 0:
            _write_ordered_marker(
                worker_marker_dir,
                "local_form_compiled",
                {"jit_cache_binding": abi["jit_cache_binding"]},
                P6_SYMBOLIC_WORKER_MARKER_ORDER,
                "task038.v19.r0.p6-slab1-mumps-symbolic.marker.v1",
            )
        matrix = dolfinx_mpc.assemble_matrix(
            compiled,
            local.local_floquet.mpc,
            bcs=[zero_boundary],
        )
        matrix.assemble()
        aij_snapshot = process_tree_snapshot(os.getpid(), "r0_p6_local_aij_assembled")
        matrix_rows = int(matrix.getSize()[0])
        matrix_info = matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
        matrix_nnz = int(matrix_info.get("nz_used", 0))
        if int(comm.rank) == 0:
            _write_ordered_marker(
                worker_marker_dir,
                "local_aij_assembled",
                {"rows": matrix_rows, "nnz": matrix_nnz},
                P6_SYMBOLIC_WORKER_MARKER_ORDER,
                "task038.v19.r0.p6-slab1-mumps-symbolic.marker.v1",
            )
        factor, analysis = analyze_mumps_p3(matrix)
        post_analysis_snapshot = process_tree_snapshot(
            os.getpid(), "r0_p6_mumps_post_analysis"
        )
        infog16 = analysis["raw_info"]["infog"].get("16")
        if type(infog16) is not int:
            raise RuntimeError("p6 MUMPS symbolic INFOG(16) is unreadable")
        post_analysis_rss = post_analysis_snapshot.get("rss_bytes")
        if type(post_analysis_rss) is not int:
            raise RuntimeError("p6 post-symbolic process-tree RSS is unreadable")
        aij_estimate = {
            "value_bytes": matrix_nnz * np.dtype(np.complex128).itemsize,
            "column_index_bytes": matrix_nnz * np.dtype(np.int32).itemsize,
            "row_pointer_bytes": (matrix_rows + 1) * np.dtype(np.int32).itemsize,
        }
        aij_estimate["total_bytes"] = sum(aij_estimate.values())
        post_build_resource_facts = {
            "pre_assembly_process_tree": pre_assembly_snapshot,
            "post_aij_process_tree": aij_snapshot,
            "post_analysis_process_tree": post_analysis_snapshot,
            "local_aij_storage_estimate": aij_estimate,
            "mumps_infog16_bytes": max(int(infog16), 0) * 1_000_000,
            "post_analysis_process_tree_rss_bytes": int(post_analysis_rss),
            "predicted_post_analysis_peak_bytes": int(
                post_analysis_rss + max(int(infog16), 0) * 1_000_000
            ),
            "mumps_conversion_extra_bytes": "not separately predicted",
            "sufficiency_claim": False,
            "authority": "full parent process-tree watchdog samples assembly, conversion, and symbolic",
        }
        factor.destroy()
        factor_destroyed = True
        if int(comm.rank) == 0:
            _write_ordered_marker(
                worker_marker_dir,
                "symbolic_complete",
                {
                    "symbolic_calls": 1,
                    "numeric_calls": 0,
                    "solve_calls": 0,
                    "infog16": infog16,
                    "post_analysis_rss_bytes": post_analysis_rss,
                },
                P6_SYMBOLIC_WORKER_MARKER_ORDER,
                "task038.v19.r0.p6-slab1-mumps-symbolic.marker.v1",
            )
        worker_record = {
            "schema": P6_SYMBOLIC_WORKER_SCHEMA,
            "phase": P6_SYMBOLIC_PHASE,
            "source_sha": source_sha,
            "input": {
                "relative_path": str(
                    Path(os.path.abspath(os.fspath(input_path))).relative_to(REPO_ROOT)
                ),
                "sha256": specification.input_sha256,
                "physical_model_sha256": specification.physical_model_sha256,
            },
            "abi": abi,
            "mpi_size": int(comm.size),
            "architecture": {
                "scope": "p6/h10 slab1 local PML diagnostic only",
                "global_matrix_materialized": False,
                "numeric_allgather": False,
                "numeric_factor_and_solve": False,
                "jit_options": dict(SAME_MESH_JIT_OPTIONS),
            },
            "p6_plan": {
                "space_global_rows": int(space.dofmap.index_map.size_global),
                "mpc_row_replacements": len(replacements),
                "interface_trace_row_counts": [int(rows.size) for rows in trace_rows],
                "audit": plan.audit,
            },
            "slab1": {
                "subdomain_id": 1,
                "rows": matrix_rows,
                "nnz": matrix_nnz,
                "boundary_row_count": int(np.asarray(boundary_rows).size),
                "form_facts": form_facts,
                "local_mesh_facts": materialized.audit["pml_local_mesh_facts"][1],
                "post_build_resource_facts": post_build_resource_facts,
            },
            "mumps": {
                "analysis": analysis,
                "numeric_performed": False,
                "solve_performed": False,
                "symbolic_calls": 1,
                "numeric_calls": 0,
                "solve_calls": 0,
                "release": {"factor_destroyed": factor_destroyed},
            },
        }
        _write_json(record_path, worker_record)
        if int(comm.rank) == 0:
            _write_ordered_marker(
                worker_marker_dir,
                "record_written",
                {"record": str(record_path.relative_to(root))},
                P6_SYMBOLIC_WORKER_MARKER_ORDER,
                "task038.v19.r0.p6-slab1-mumps-symbolic.marker.v1",
            )
        return_code = 0
    finally:
        if factor is not None and not factor_destroyed:
            factor.destroy()
        if matrix is not None:
            matrix.destroy()
        if materialized is not None:
            destroy_materialized_pml_quartile_plan(materialized)
        _destroy_mpc_bundle(levels)
        if int(comm.rank) == 0 and "return_code" in locals() and return_code == 0:
            _write_ordered_marker(
                worker_marker_dir,
                "release_complete",
                {"factor_destroyed": factor_destroyed},
                P6_SYMBOLIC_WORKER_MARKER_ORDER,
                "task038.v19.r0.p6-slab1-mumps-symbolic.marker.v1",
            )
    return return_code


def run_p6_symbolic_parent(
    root: Path,
    record_path: Path,
    source_sha: str,
    input_path: Path,
) -> int:
    from benchmarks.run_task038_full3d_physical_pcoarse_q1 import (
        _cache_snapshot,
        _prepare_parent_root,
        _process_summary,
        _run_parent_child,
    )

    root, cache = _prepare_parent_root(root)
    record_path = Path(os.path.abspath(os.fspath(record_path)))
    if record_path.parent != root:
        raise ValueError("p6 symbolic parent record must be directly below artifact root")
    raw = root / "raw"
    marker_dir = root / "markers"
    raw.mkdir(exist_ok=False)
    marker_dir.mkdir(exist_ok=False)
    _write_ordered_marker(
        marker_dir,
        "paths_ready",
        {"source_sha": source_sha, "phase": P6_SYMBOLIC_PHASE},
        P6_SYMBOLIC_PARENT_MARKER_ORDER,
        "task038.v19.r0.p6-slab1-mumps-symbolic.parent-marker.v1",
    )
    source = None
    budget = None
    worker_result = None
    error = None
    try:
        source = _p6_symbolic_source_facts(source_sha, input_path)
        budget = _p6_symbolic_launch_budget()
        preflight = {
            "schema": "task038.v19.r0.p6-slab1-mumps-symbolic.preflight.v1",
            **source,
            **budget,
            "python": str(sys.executable),
            "python_prefix": str(sys.prefix),
            "qualified_activation": os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION"),
            "threads": {
                name: os.environ.get(name, "1")
                for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
            },
        }
        _write_json(raw / "p6_symbolic_preflight.json", preflight)
        _write_ordered_marker(
            marker_dir,
            "abi_ready",
            {
                "qualified_activation": preflight["qualified_activation"],
                "python": preflight["python"],
                "python_prefix": preflight["python_prefix"],
                "threads": preflight["threads"],
                "worker_abi_checked_in_worker_record": True,
            },
            P6_SYMBOLIC_PARENT_MARKER_ORDER,
            "task038.v19.r0.p6-slab1-mumps-symbolic.parent-marker.v1",
        )
        cache_initial = _cache_snapshot(cache)
        worker_record = raw / "worker_record.json"
        worker_result = _run_parent_child(
            _p6_symbolic_worker_command(
                root, worker_record, source_sha, Path(os.path.abspath(os.fspath(input_path)))
            ),
            root / "parent_process.jsonl",
            "r0_p6_slab1_mumps_symbolic",
            root / "worker.stdout.log",
            root / "worker.stderr.log",
            rss_watchdog_bytes=budget["launch_cap_bytes"],
            rss_warning_bytes=budget["warning_bytes"],
        )
        cache_after = _cache_snapshot(cache)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        cache_initial = locals().get("cache_initial")
        cache_after = locals().get("cache_after")
    worker_record = raw / "worker_record.json"
    process_summary = None
    sample_path = root / "parent_process.jsonl"
    if sample_path.is_file():
        process_summary = _process_summary(sample_path)
    worker_record_present = worker_record.is_file()
    worker_complete = bool(
        worker_result is not None
        and worker_result["returncode"] == 0
        and worker_result["stop_reason"] is None
        and worker_result["process_group_gone"] is True
        and worker_record_present
    )
    worker_resource_stop = bool(
        worker_result is not None
        and worker_result.get("stop_reason") in P6_RESOURCE_STOP_REASONS
    )
    if worker_result is not None:
        _write_ordered_marker(
            marker_dir,
            "worker_complete",
            {
                "returncode": worker_result["returncode"],
                "stop_reason": worker_result["stop_reason"],
                "process_group_gone": worker_result["process_group_gone"],
                "peak_rss_bytes": worker_result["peak_rss_bytes"],
                "max_swap_bytes": worker_result["max_swap_bytes"],
            },
            P6_SYMBOLIC_PARENT_MARKER_ORDER,
            "task038.v19.r0.p6-slab1-mumps-symbolic.parent-marker.v1",
        )
    parent_record = {
        "schema": P6_SYMBOLIC_PARENT_SCHEMA,
        "phase": P6_SYMBOLIC_PHASE,
        "source": source,
        "status": (
            "RAW_COMPLETE_PENDING_REVIEW"
            if error is None and worker_complete
            else "RAW_INCOMPLETE_PENDING_REVIEW"
        ),
        "classification": (
            "R0_P6_SYMBOLIC_ANALYSIS_COMPLETE_PENDING_REVIEW"
            if error is None and worker_complete
            else "R0_P6_SYMBOLIC_RESOURCE_CONTROLLED_STOP"
            if error is None and worker_resource_stop
            else "R0_P6_SYMBOLIC_PRECHECK_OR_ENGINEERING_STOP"
        ),
        "command": {
            "argv": [str(value) for value in sys.argv],
            "worker_argv": [] if worker_result is None else worker_result["argv"],
            "cwd": str(REPO_ROOT),
        },
        "paths": {
            "jit_cache": "jit_cache",
            "preflight": "raw/p6_symbolic_preflight.json",
            "worker_record": "raw/worker_record.json",
            "worker_markers": "raw/worker_markers",
            "process_samples": "parent_process.jsonl",
        },
        "budget": budget,
        "cache": {
            "initial": locals().get("cache_initial"),
            "after_worker": locals().get("cache_after"),
        },
        "worker": (
            None
            if worker_result is None
            else {
                **worker_result,
                "record_present": worker_record_present,
                "record_sha256": (
                    _sha256_file(worker_record) if worker_record.is_file() else None
                ),
                "stdout_sha256": (
                    _sha256_file(root / "worker.stdout.log")
                    if (root / "worker.stdout.log").is_file()
                    else None
                ),
                "stderr_sha256": (
                    _sha256_file(root / "worker.stderr.log")
                    if (root / "worker.stderr.log").is_file()
                    else None
                ),
            }
        ),
        "process": process_summary,
        "numeric_factor_and_solve": False,
        "worker_complete": worker_complete,
        "error": error,
    }
    _write_json(record_path, parent_record)
    _write_ordered_marker(
        marker_dir,
        "record_written",
        {"record": str(record_path.relative_to(root))},
        P6_SYMBOLIC_PARENT_MARKER_ORDER,
        "task038.v19.r0.p6-slab1-mumps-symbolic.parent-marker.v1",
    )
    _write_ordered_marker(
        marker_dir,
        "release_complete",
        {
            "record": str(record_path.relative_to(root)),
            "worker_released": bool(
                worker_result is not None
                and worker_result.get("process_group_gone") is True
            ),
        },
        P6_SYMBOLIC_PARENT_MARKER_ORDER,
        "task038.v19.r0.p6-slab1-mumps-symbolic.parent-marker.v1",
    )
    return int(
        error is not None
        or not worker_complete
    )


def run_r0(root: Path, record_path: Path, source_sha: str, input_path: Path) -> int:
    if root.exists():
        raise FileExistsError(f"R0 artifact root already exists: {root}")
    record_path = record_path.absolute()
    root.mkdir()
    if record_path.parent != root:
        raise ValueError("R0 record must be directly below artifact root")
    raw = root / "raw"
    marker_dir = root / "markers"
    raw.mkdir()
    marker_dir.mkdir()
    _write_marker(marker_dir, "paths_ready", {"profile": PROFILE, "source_sha": source_sha})
    from src.io.input_validation import load_and_resolve, simulation_config_3d_from_normalized
    from mpi4py import MPI
    from petsc4py import PETSc

    specification = load_and_resolve(input_path)
    if specification.solver["preconditioner"] != PROFILE:
        raise ValueError("R0 input must select the explicit V19 PML profile")
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    abi = {
        "qualified_activation": os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION"),
        "python": sys.executable,
        "python_prefix": sys.prefix,
        "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
        "petsc_int_type": str(np.dtype(PETSc.IntType)),
        "mpi_size": int(MPI.COMM_SELF.size),
        "library_paths": {
            name: os.environ.get(name, "")
            for name in ("PETSC_DIR", "SLEPC_DIR", "CMAKE_PREFIX_PATH", "LD_LIBRARY_PATH")
        },
    }
    if (
        abi["qualified_activation"] != "1"
        or abi["petsc_scalar_type"] != "complex128"
        or abi["petsc_int_type"] != "int32"
        or abi["mpi_size"] != MPI_SIZE
    ):
        raise RuntimeError("R0 qualified complex MPI1 ABI preflight failed")
    _write_marker(marker_dir, "abi_ready", abi)
    p2 = _p2_fixture(cfg, MPI.COMM_SELF)
    _write_marker(marker_dir, "p2_fixture_complete", {"local_action_relative": p2["local_action_relative"]})
    p6 = _p6_inventory(cfg, MPI.COMM_SELF)
    _write_marker(marker_dir, "p6_inventory_complete", {"global_aij_nnz": p6["global_structure"]["global_aij_nnz"]})
    pml_thicknesses = [
        item["pml_thicknesses_nm"]
        for item in p6["pml_audit"]["pml_local_mesh_facts"]
    ]
    record = {
        "schema": R0_SCHEMA,
        "phase": PHASE,
        "profile": PROFILE,
        "branch": BRANCH,
        "source_sha": source_sha,
        "abi": abi,
        "input": {
            "relative_path": str(input_path.resolve().relative_to(REPO_ROOT)),
            "sha256": specification.input_sha256,
            "physical_model_sha256": specification.physical_model_sha256,
        },
        "mpi_size": MPI_SIZE,
        "architecture": {
            "formula": "z=0,r=q; B_j w_j=F_j R_j r; dz_j=R_j^H D_j E_j w_j; r<-r-A dz_j",
            "sweep_order": list(SWEEP_ORDER),
            "core_count": 4,
            "overlap_layers": 1,
            "pml_layers": PML_LAYER_COUNT,
            "outer_physical_boundary": "streaming DtN retained",
            "global_matrix_materialized": False,
            "numeric_allgather": False,
        },
        "pml_profile": {
            "formula": "s(t)=1+i*sigma_max*(t/delta)^2",
            "target_one_way_amplitude": 0.01,
            "subdomain_thicknesses_nm": pml_thicknesses,
            "subdomain_facts": [
                {
                    "subdomain_id": index,
                    "left": pml_profile_facts(
                        thickness["left"]
                    ) if thickness["left"] > 0.0 else None,
                    "right": pml_profile_facts(
                        thickness["right"]
                    ) if thickness["right"] > 0.0 else None,
                }
                for index, thickness in enumerate(pml_thicknesses)
            ],
        },
        "p2_fixture": p2,
        "p6_inventory": p6,
        "outer_solve": "not_run_R0",
    }
    raw_record = raw / "r0_record.json"
    _write_json(raw_record, record)
    _write_marker(marker_dir, "record_written", {"record": str(raw_record.relative_to(root))})
    _write_json(
        record_path,
        {
            "schema": R0_SCHEMA,
            "raw_record": str(raw_record.relative_to(root)),
            "raw_record_sha256": _sha256_file(raw_record),
            "source_sha": source_sha,
            "profile": PROFILE,
        },
    )
    _write_marker(marker_dir, "release_complete", {"record": str(record_path.relative_to(root))})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--mode", choices=("parent", "worker"), required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--mpi-size", type=int, required=True)
    args = parser.parse_args(argv)
    if args.mpi_size != MPI_SIZE:
        parser.error("V19 R0 diagnostics are fixed to MPI1")
    if args.phase == PHASE:
        if args.mode != "parent":
            parser.error("phase=r0 only accepts mode=parent")
        return run_r0(args.artifact_root, args.record, args.source_sha, args.input)
    if args.phase == P6_SYMBOLIC_PHASE:
        if args.mode == "parent":
            return run_p6_symbolic_parent(
                args.artifact_root, args.record, args.source_sha, args.input
            )
        return _p6_symbolic_worker(
            args.artifact_root,
            args.record,
            args.source_sha,
            args.input,
            args.mpi_size,
        )
    parser.error(f"unsupported V19 phase: {args.phase}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
