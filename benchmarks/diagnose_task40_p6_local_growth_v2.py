"""Bounded Task40 p6 local-block inventory and streamed modal action diagnostic.

Builds the exact G0 p6 mesh and physical volume form, extracts one real cell
per material tag, and measures local LU/Schur/recovery plus a synthetic,
resampled port-coupling stress in fixed column batches. It never assembles a
global condensation matrix, global port square block, or global factor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import warnings
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import LinAlgWarning, lu_factor, lu_solve

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.io import load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from src.solvers.fullspace_physical_intermediate_runtime import fine_volume_quadrature_metadata
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
from src.solvers.hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
    _cell_integral_kernels,
    _cell_tag_array,
    _orient_cell_tensor,
    _tabulate_raw_tensor_class,
)
from src.solvers.common_3d_forms import _build_physical_volume_terms


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    return hashlib.sha256(
        repr((array.shape, str(array.dtype))).encode() + array.tobytes(order="C")
    ).hexdigest()


def _form_with_metadata(form: Any, metadata: dict[str, Any]):
    import ufl

    return ufl.Form(
        tuple(
            integral.reconstruct(metadata={**(integral.metadata() or {}), **metadata})
            for integral in form.integrals()
        )
    )


def _git_facts() -> dict[str, str]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD"], cwd=ROOT,
        check=True, capture_output=True,
    ).stdout
    return {
        "head_sha": head,
        "tracked_worktree_diff_sha256": hashlib.sha256(diff).hexdigest(),
    }


def _backing_inventory(values: list[np.ndarray]) -> dict[str, int]:
    owners: dict[int, int] = {}
    for value in values:
        owner: Any = value
        while isinstance(getattr(owner, "base", None), np.ndarray):
            owner = owner.base
        owners[id(owner)] = int(owner.nbytes)
    return {"unique_backings": len(owners), "unique_backing_bytes": int(sum(owners.values()))}


def _complex_random(rng: np.random.Generator, shape: tuple[int, ...], scale: float) -> np.ndarray:
    value = rng.standard_normal(shape) + 1j * rng.standard_normal(shape)
    value = np.asarray(value / math.sqrt(scale), dtype=np.complex128, order="C")
    return value


def _make_bank(rng: np.random.Generator, ni: int, nt: int, bank_modes: int) -> dict[str, np.ndarray]:
    return {
        "Bi": _complex_random(rng, (ni, bank_modes), ni),
        "Di": _complex_random(rng, (bank_modes, ni), ni),
        "Bt": _complex_random(rng, (nt, bank_modes), nt),
        "Dt": _complex_random(rng, (bank_modes, nt), nt),
        "trace_modes": _complex_random(rng, (nt, bank_modes), nt),
    }


def _select_columns(bank: np.ndarray, indices: np.ndarray, multiplier: np.ndarray) -> np.ndarray:
    values = np.take(bank, indices, axis=1)
    values *= multiplier[None, :]
    return np.ascontiguousarray(values)


def _select_rows(bank: np.ndarray, indices: np.ndarray, multiplier: np.ndarray) -> np.ndarray:
    values = np.take(bank, indices, axis=0)
    values *= multiplier[:, None]
    return np.ascontiguousarray(values)


def _streamed_modal_action(
    *,
    factor: tuple[np.ndarray, np.ndarray],
    Aii: np.ndarray,
    Ait: np.ndarray,
    Ati: np.ndarray,
    Xit: np.ndarray,
    bank: dict[str, np.ndarray],
    alpha: np.ndarray,
    trace_vector: np.ndarray,
    batch_size: int,
    resident_arrays: list[np.ndarray] | None = None,
) -> dict[str, Any]:
    """Apply both directions with two fixed-batch passes and complete feedback."""
    ni, nt = Aii.shape[0], Ait.shape[1]
    mode_count = int(alpha.size)
    bank_modes = int(bank["Bi"].shape[1])
    resident_arrays = [] if resident_arrays is None else resident_arrays
    w = np.zeros(ni, dtype=np.complex128)
    trace_from_port = np.zeros(nt, dtype=np.complex128)
    port_from_trace = np.zeros(mode_count, dtype=np.complex128)
    port_feedback = np.zeros(mode_count, dtype=np.complex128)
    local_trace_load = Ait @ trace_vector
    generation_seconds = 0.0
    first_pass_seconds = 0.0
    second_pass_seconds = 0.0
    recovery_seconds = 0.0
    closure_max = 0.0
    known_live_peak_bytes = 0
    known_live_peak_backings = 0
    processed_columns = 0

    def remember(*arrays: np.ndarray) -> None:
        nonlocal known_live_peak_bytes, known_live_peak_backings
        inventory = _backing_inventory(
            [*resident_arrays, *bank.values(), factor[0], factor[1], alpha,
             trace_vector, w, trace_from_port, port_from_trace, port_feedback,
             local_trace_load, *arrays]
        )
        known_live_peak_bytes = max(known_live_peak_bytes, inventory["unique_backing_bytes"])
        known_live_peak_backings = max(known_live_peak_backings, inventory["unique_backings"])

    # Pass 1 streams every port column into a single interior response and trace response.
    for start in range(0, mode_count, batch_size):
        stop = min(start + batch_size, mode_count)
        indices = np.arange(start, stop, dtype=np.int64) % bank_modes
        cycles = np.arange(start, stop, dtype=np.int64) // bank_modes
        multiplier = (1.0 + 0.01 * cycles) * np.exp(0.13j * cycles)
        generation_start = time.perf_counter()
        Bi = _select_columns(bank["Bi"], indices, multiplier)
        Bt = _select_columns(bank["Bt"], indices, multiplier)
        generation_seconds += time.perf_counter() - generation_start
        alpha_batch = alpha[start:stop]
        reduction_start = time.perf_counter()
        XiB = lu_solve(factor, Bi, check_finite=False)
        Vti_XiB = Ati @ XiB
        Bhat = Bt - Vti_XiB
        w += XiB @ alpha_batch
        trace_from_port += Bhat @ alpha_batch
        first_pass_seconds += time.perf_counter() - reduction_start
        processed_columns += stop - start
        remember(indices, cycles, multiplier, Bi, Bt, alpha_batch, XiB, Vti_XiB, Bhat)
        del indices, cycles, multiplier, Bi, Bt, alpha_batch, XiB, Vti_XiB, Bhat

    # Pass 2 regenerates the same row blocks. The shared w contains all columns,
    # including those in later batches, so Di @ w includes cross-batch feedback.
    for start in range(0, mode_count, batch_size):
        stop = min(start + batch_size, mode_count)
        indices = np.arange(start, stop, dtype=np.int64) % bank_modes
        cycles = np.arange(start, stop, dtype=np.int64) // bank_modes
        multiplier = (1.0 + 0.01 * cycles) * np.exp(0.13j * cycles)
        generation_start = time.perf_counter()
        Bi = _select_columns(bank["Bi"], indices, multiplier)
        Di = _select_rows(bank["Di"], indices, multiplier)
        Dt = _select_rows(bank["Dt"], indices, multiplier)
        generation_seconds += time.perf_counter() - generation_start
        alpha_batch = alpha[start:stop]
        action_start = time.perf_counter()
        Di_Xit = Di @ Xit
        Dhat = Dt - Di_Xit
        port_from_trace[start:stop] = Dhat @ trace_vector
        port_feedback[start:stop] = Di @ w
        second_pass_seconds += time.perf_counter() - action_start

        recovery_start = time.perf_counter()
        Bi_alpha = Bi * alpha_batch[None, :]
        local_load = local_trace_load[:, None] + Bi_alpha
        recovered = lu_solve(factor, -local_load, check_finite=False)
        applied = Aii @ recovered
        closure_matrix = applied + local_load
        denominators = np.maximum(np.linalg.norm(local_load, axis=0), np.finfo(float).tiny)
        closure = np.linalg.norm(closure_matrix, axis=0) / denominators
        closure_max = max(closure_max, float(np.max(closure)))
        recovery_seconds += time.perf_counter() - recovery_start
        remember(
            indices, cycles, multiplier, Bi, Di, Dt, alpha_batch, Di_Xit,
            Dhat, Bi_alpha, local_load, recovered, applied, closure_matrix,
            denominators, closure,
        )
        del indices, cycles, multiplier, Bi, Di, Dt, alpha_batch, Di_Xit, Dhat
        del Bi_alpha, local_load, recovered, applied, closure_matrix, denominators, closure

    port_total = port_from_trace + port_feedback
    remember(port_total)
    finite = all(
        np.isfinite(value).all()
        for value in (alpha, trace_vector, w, trace_from_port, port_from_trace, port_feedback, port_total)
    )
    # Explicit-array upper bound includes all resident NumPy backings, O(M) input/
    # outputs, and a deliberately padded fixed-batch scratch allowance. BLAS-private
    # workspaces are excluded and separately captured by process RUSAGE high water.
    resident = _backing_inventory(
        [*resident_arrays, *bank.values(), factor[0], factor[1]]
    )["unique_backing_bytes"]
    vector_complex_entries = 4 * mode_count + 2 * ni + 3 * nt
    vector_bytes = 16 * vector_complex_entries
    max_batch = min(mode_count, batch_size)
    batch_scratch_complex_entries = max_batch * (16 * ni + 12 * nt) + 4 * max_batch
    fixed_batch_scratch_upper = 16 * batch_scratch_complex_entries + 8192
    return {
        "w": w,
        "trace_from_port": trace_from_port,
        "port_from_trace": port_from_trace,
        "port_feedback": port_feedback,
        "port_total": port_total,
        "max_nonzero_rhs_local_recovery_relative_closure": float(closure_max),
        "all_outputs_finite": bool(finite),
        "processed_columns_first_pass": int(processed_columns),
        "processed_rows_second_pass": int(mode_count),
        "known_live_numpy_backing_bytes_lower_bound": int(known_live_peak_bytes),
        "known_live_numpy_backing_count_lower_bound": int(known_live_peak_backings),
        "resident_numpy_backing_bytes_in_upper_bound": int(resident),
        "O_M_vector_backing_bytes": int(vector_bytes),
        "fixed_batch_explicit_numpy_scratch_upper_bound_bytes": int(fixed_batch_scratch_upper),
        "explicit_array_scenario_upper_bound_bytes": int(resident + vector_bytes + fixed_batch_scratch_upper),
        "scratch_bound_excludes": "opaque BLAS/LAPACK library workspace; process RUSAGE high-water includes it",
        "timings": {
            "coupling_regeneration_seconds": float(generation_seconds),
            "first_pass_local_reduction_and_accumulation_seconds": float(first_pass_seconds),
            "second_pass_port_action_seconds": float(second_pass_seconds),
            "second_pass_local_recovery_and_closure_seconds": float(recovery_seconds),
        },
    }


def _mode_stress(
    *,
    factor: tuple[np.ndarray, np.ndarray],
    Aii: np.ndarray,
    Ait: np.ndarray,
    Ati: np.ndarray,
    Xit: np.ndarray,
    bank: dict[str, np.ndarray],
    mode_sizes: list[int],
    batch_size: int,
    seed: int,
    resident_arrays: list[np.ndarray] | None = None,
) -> list[dict[str, Any]]:
    ni, nt = Aii.shape[0], Ait.shape[1]
    bank_modes = int(bank["Bi"].shape[1])
    bank_bytes = _backing_inventory(list(bank.values()))["unique_backing_bytes"]
    output: list[dict[str, Any]] = []
    for mode_count in mode_sizes:
        rng = np.random.default_rng(seed + int(mode_count))
        alpha = _complex_random(rng, (mode_count,), 1)
        trace_vector = _complex_random(rng, (nt,), nt)
        wall_start = time.perf_counter()
        cpu_start = time.process_time()
        action = _streamed_modal_action(
            factor=factor, Aii=Aii, Ait=Ait, Ati=Ati, Xit=Xit, bank=bank,
            alpha=alpha, trace_vector=trace_vector, batch_size=batch_size,
            resident_arrays=resident_arrays,
        )
        wall_seconds = time.perf_counter() - wall_start
        cpu_seconds = time.process_time() - cpu_start
        closure = action["max_nonzero_rhs_local_recovery_relative_closure"]
        record = {
            "mode_count": int(mode_count),
            "classification": "MEASURED_SYNTHETIC_RESAMPLED_CHANNEL_STRESS",
            "physical_model": False,
            "bank_mode_count": bank_modes,
            "resampling": "cycle modulo bank modes with common per-column complex phase and 1% per-cycle amplitude ramp",
            "frozen_complete_alpha_sha256": _array_sha256(alpha),
            "frozen_trace_vector_sha256": _array_sha256(trace_vector),
            "same_alpha_and_trace_used_in_both_passes": True,
            "two_pass_complete_cross_batch_feedback": True,
            "feedback_definition": "pass 1 w=sum_j(Vii^-1 Bi_j alpha_j); pass 2 computes every output row Di_i w, so cross-batch pairs are included",
            "direct_H_block": "zero in the synthetic stress; no dense M by M H block is formed",
            "fixed_column_batch": int(batch_size),
            "batch_count_per_pass": int(math.ceil(mode_count / batch_size)),
            "max_batch_columns": int(min(mode_count, batch_size)),
            "processed_mode_columns_first_pass": int(action["processed_columns_first_pass"]),
            "processed_mode_rows_second_pass": int(action["processed_rows_second_pass"]),
            "no_mode_square_allocation": True,
            "largest_mode_square_scratch_shape": [0, 0],
            "largest_mode_square_scratch_bytes": 0,
            "base_bank_unique_backing_bytes": int(bank_bytes),
            "known_live_numpy_backing_bytes_lower_bound": int(action["known_live_numpy_backing_bytes_lower_bound"]),
            "known_live_numpy_backing_count_lower_bound": int(action["known_live_numpy_backing_count_lower_bound"]),
            "fixed_batch_explicit_numpy_scratch_upper_bound_bytes": int(action["fixed_batch_explicit_numpy_scratch_upper_bound_bytes"]),
            "explicit_array_scenario_upper_bound_bytes": int(action["explicit_array_scenario_upper_bound_bytes"]),
            "scratch_bound_excludes": action["scratch_bound_excludes"],
            "wall_seconds": float(wall_seconds),
            "process_cpu_seconds": float(cpu_seconds),
            "process_cpu_to_wall_ratio": float(cpu_seconds / max(wall_seconds, np.finfo(float).tiny)),
            **action["timings"],
            "max_nonzero_rhs_local_recovery_relative_closure": float(closure),
            "all_outputs_finite": bool(action["all_outputs_finite"]),
            "closure_limit": 1.0e-10,
            "diagnostic_pass": bool(closure <= 1.0e-10 and action["all_outputs_finite"]),
            "output_vector_sha256": {
                name: _array_sha256(action[name])
                for name in ("w", "trace_from_port", "port_from_trace", "port_feedback", "port_total")
            },
            "output_vector_norms": {
                name: float(np.linalg.norm(action[name]))
                for name in ("w", "trace_from_port", "port_from_trace", "port_feedback", "port_total")
            },
            "local_dimensions": {"interior": ni, "trace": nt},
        }
        output.append(record)
        print(
            f"P6_MODE_STRESS mode_count={mode_count} batches/pass={record['batch_count_per_pass']} "
            f"wall={wall_seconds:.3f}s cpu={cpu_seconds:.3f}s closure={closure:.3e}",
            flush=True,
        )
    return output


def _process_peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value * 1024 if sys.platform.startswith("linux") else value


def run(args: argparse.Namespace) -> dict[str, Any]:
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("bounded Task40 P6 local witness is MPI1-only")
    if args.batch_size <= 0 or args.bank_modes <= 0:
        raise ValueError("batch size and bank mode count must be positive")
    if args.max_tags <= 0:
        raise ValueError("max-tags must be positive")
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    resolved = load_and_resolve(args.input)
    cfg = simulation_config_3d_from_normalized(resolved.as_jsonable())
    if int(cfg.nedelec_degree) != 6:
        raise ValueError("local witness requires p6 input")
    campaign_start = time.perf_counter()
    result: dict[str, Any] = {
        "schema": "task40extra.p6-local-block-inventory-v2",
        "status": "STARTED",
        "official_pde": False,
        "global_condensation_matrix_or_factor": False,
        "input_path": str(args.input.resolve()),
        "input_sha256": _sha256(args.input),
        "resolved_physical_model_sha256": resolved.physical_model_sha256,
        "source": _git_facts(),
        "diagnostic_script_sha256": _sha256(Path(__file__).resolve()),
        "p6_cell_preparation_runner_sha256": _sha256(ROOT / "benchmarks/run_task39extra_v29_p6_tensor_pair.py"),
        "local_tensor_assembly_sha256": _sha256(ROOT / "src/solvers/hcurl_assembly_time_condensation.py"),
        "production_action_source_sha256": _sha256(ROOT / "src/solvers/p6_cell_condensed_action.py"),
        "mode_sizes": [int(value) for value in args.mode_sizes],
        "bank_mode_count": int(args.bank_modes),
        "fixed_column_batch": int(args.batch_size),
        "synthetic_channel_stress_warning": "Only channel-vector dimensions and local action formulas are stress-tested; no complete higher-M physical port model is asserted.",
        "local_cells": [],
    }
    mesh_start = time.perf_counter()
    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_WORLD, (6,), include_positive_coefficients=False
    )
    mesh_seconds = time.perf_counter() - mesh_start
    mesh = levels["mesh"]
    space = levels["spaces"][6]
    owned_cells = int(mesh.topology.index_map(3).size_local)
    result["mesh_and_space"] = {
        "build_wall_seconds": float(mesh_seconds),
        "owned_cells": owned_cells,
        "p6_global_space_dofs": int(space.dofmap.index_map.size_global),
        "space_element_dimension": int(space.element.space_dimension),
        "mesh_geometry_coordinate_sha256": _array_sha256(np.asarray(mesh.geometry.x)),
        "mesh_cell_tags_histogram": {
            str(int(tag)): int(np.count_nonzero(_cell_tag_array(
                levels["mesh_data"].cell_tags, owned_cells
            ) == tag))
            for tag in np.unique(_cell_tag_array(levels["mesh_data"].cell_tags, owned_cells))
        },
    }
    quadrature_metadata, quadrature_records = fine_volume_quadrature_metadata(levels, cfg)
    import ufl
    from dolfinx import fem
    curl_form, mass_form = _build_physical_volume_terms(
        cfg, ufl.TrialFunction(space), ufl.TestFunction(space),
        ufl.Measure("dx", domain=mesh, subdomain_data=levels["mesh_data"].cell_tags),
    )
    full_form = _form_with_metadata(curl_form, dict(quadrature_metadata[0])) + _form_with_metadata(
        mass_form, dict(quadrature_metadata[1])
    )
    compile_start = time.perf_counter()
    compiled = fem.form(full_form, jit_options=dict(SAME_MESH_JIT_OPTIONS))
    compile_seconds = time.perf_counter() - compile_start
    kernels = _cell_integral_kernels(compiled, sum_duplicate_cell_integrals=True)
    result["form"] = {
        "compile_wall_seconds": float(compile_seconds),
        "ufcx_signature": compiled.module.ffi.string(compiled.ufcx_form.signature).decode("ascii"),
        "quadrature_metadata": [dict(value) for value in quadrature_metadata],
        "quadrature_records": list(quadrature_records),
        "kernel_inventory": {
            str(int(tag)): int(len(value) if isinstance(value, (tuple, list)) else 1)
            for tag, value in sorted(kernels.items())
        },
        "scope": "exact Task40 G0 p6 physical curl-plus-mass cell integrals",
    }
    tags = _cell_tag_array(levels["mesh_data"].cell_tags, owned_cells)
    mesh.topology.create_entity_permutations()
    permutations = np.asarray(mesh.topology.get_cell_permutation_info(), dtype=np.uint32)
    element = space.element.basix_element
    dimension = int(space.element.space_dimension)
    interior = np.asarray(element.entity_dofs[3][0], dtype=np.int32)
    trace = np.setdiff1d(np.arange(dimension, dtype=np.int32), interior)
    if (dimension, len(interior), len(trace)) != (882, 450, 432):
        raise RuntimeError(
            f"unexpected local dimensions {(dimension, len(interior), len(trace))}; expected (882, 450, 432)"
        )
    selected_tags = [int(value) for value in np.unique(tags)[: args.max_tags]]
    rng_seed_base = int(args.seed)
    for tag_index, tag in enumerate(selected_tags):
        cell = int(np.flatnonzero(tags == tag)[0])
        geometry_dofs = np.asarray(mesh.geometry.dofmap[cell], dtype=np.int32)
        physical_coordinates = np.asarray(mesh.geometry.x[geometry_dofs], dtype=np.float64)
        canonical_coordinates, cell_widths = _canonical_axis_aligned_coordinates(
            mesh, cell, tolerance=1.0e-11, preserve_exact_geometry=True
        )
        assembly_start = time.perf_counter()
        native = _tabulate_raw_tensor_class(
            compiled, kernels, canonical_coordinates, tag=tag, dimension=dimension
        )
        _orient_cell_tensor(element, native, permutations[cell])
        assembly_seconds = time.perf_counter() - assembly_start
        Aii = np.ascontiguousarray(native[np.ix_(interior, interior)])
        Ait = np.ascontiguousarray(native[np.ix_(interior, trace)])
        Ati = np.ascontiguousarray(native[np.ix_(trace, interior)])
        Att = np.ascontiguousarray(native[np.ix_(trace, trace)])
        factor_start = time.perf_counter()
        with warnings.catch_warnings(record=True) as factor_warnings:
            warnings.simplefilter("always", LinAlgWarning)
            factor = lu_factor(Aii, overwrite_a=False, check_finite=True)
        factor_seconds = time.perf_counter() - factor_start
        factor_warning_messages = [str(item.message) for item in factor_warnings]
        reduction_start = time.perf_counter()
        Xit = lu_solve(factor, Ait, check_finite=False)
        schur = Att - Ati @ Xit
        reduction_seconds = time.perf_counter() - reduction_start
        closure_rng = np.random.default_rng(rng_seed_base + tag_index)
        trace_rhs = _complex_random(closure_rng, (len(trace),), len(trace))
        interior_rhs = _complex_random(closure_rng, (len(interior),), len(interior))
        local_rhs = interior_rhs - Ait @ trace_rhs
        recovery_start = time.perf_counter()
        recovered = lu_solve(factor, local_rhs, check_finite=False)
        residual = Aii @ recovered + Ait @ trace_rhs - interior_rhs
        local_closure = float(
            np.linalg.norm(residual) / max(float(np.linalg.norm(interior_rhs)), np.finfo(float).tiny)
        )
        recovery_seconds = time.perf_counter() - recovery_start
        dofs = np.asarray(space.dofmap.cell_dofs(cell), dtype=np.int64)
        cell_record: dict[str, Any] = {
            "material_tag": tag,
            "cell_local_index": cell,
            "cell_permutation_info": int(permutations[cell]),
            "physical_geometry_coordinates": physical_coordinates.tolist(),
            "canonical_cell_coordinates_sha256": _array_sha256(canonical_coordinates),
            "cell_widths": [float(value) for value in cell_widths],
            "local_dof_map_count": int(dofs.size),
            "local_dof_map_sha256": _array_sha256(dofs),
            "local_tensor_shape": list(native.shape),
            "local_tensor_dtype": str(native.dtype),
            "local_tensor_sha256": _array_sha256(native),
            "local_tensor_backing_bytes": int(native.nbytes),
            "interior_block_shape": list(Aii.shape),
            "trace_block_shape": list(Att.shape),
            "interior_block_backing_bytes": int(Aii.nbytes),
            "interior_lu_backing_bytes": int(factor[0].nbytes),
            "interior_lu_pivot_backing_bytes": int(factor[1].nbytes),
            "interior_lu_pivot_min": int(np.min(factor[1])) if factor[1].size else None,
            "interior_lu_pivot_max": int(np.max(factor[1])) if factor[1].size else None,
            "schur_shape": list(schur.shape),
            "schur_backing_bytes": int(schur.nbytes),
            "schur_sha256": _array_sha256(schur),
            "local_nonzero_rhs_recovery_relative_closure": local_closure,
            "local_closure_limit": 1.0e-10,
            "local_closure_pass": bool(local_closure <= 1.0e-10 and not factor_warning_messages),
            "factor_warnings": factor_warning_messages,
            "assembly_wall_seconds": float(assembly_seconds),
            "lu_factor_wall_seconds": float(factor_seconds),
            "local_schur_reduction_wall_seconds": float(reduction_seconds),
            "nonzero_rhs_recovery_wall_seconds": float(recovery_seconds),
            "retained_block_backing_inventory": _backing_inventory(
                [native, Aii, Ait, Ati, Att, factor[0], factor[1], Xit, schur,
                 trace_rhs, interior_rhs, local_rhs, recovered, residual]
            ),
            "mode_growth_runs": [],
        }
        bank_rng = np.random.default_rng(rng_seed_base + 1000 + tag_index)
        bank = _make_bank(bank_rng, len(interior), len(trace), args.bank_modes)
        cell_record["synthetic_resampled_bank"] = {
            "seed": rng_seed_base + 1000 + tag_index,
            "array_shapes": {name: list(value.shape) for name, value in bank.items()},
            "array_backing_bytes": {name: int(value.nbytes) for name, value in bank.items()},
            "total_unique_backing_bytes": _backing_inventory(list(bank.values()))["unique_backing_bytes"],
            "meaning": "deterministic synthetic coupling vectors used only for bounded dimension/action stress, not derived from a complete physical port model",
        }
        cell_record["mode_growth_runs"] = _mode_stress(
            factor=factor, Aii=Aii, Ait=Ait, Ati=Ati, Xit=Xit,
            bank=bank, mode_sizes=args.mode_sizes, batch_size=args.batch_size,
            seed=rng_seed_base + 2000 + tag_index,
            resident_arrays=[native, Aii, Ait, Ati, Att, factor[0], factor[1],
                             Xit, schur, trace_rhs, interior_rhs, local_rhs,
                             recovered, residual],
        )
        cell_record["all_mode_growth_diagnostics_pass"] = bool(
            all(item["diagnostic_pass"] for item in cell_record["mode_growth_runs"])
        )
        result["local_cells"].append(cell_record)
        print(
            f"P6_LOCAL_CELL tag={tag} cell={cell} closure={local_closure:.3e} "
            f"assemble={assembly_seconds:.3f}s factor={factor_seconds:.3f}s",
            flush=True,
        )
        del bank, native, Aii, Ait, Ati, Att, factor, Xit, schur
        del trace_rhs, interior_rhs, local_rhs, recovered, residual
    local_closures_pass = bool(result["local_cells"]) and all(
        cell["local_closure_pass"] for cell in result["local_cells"]
    )
    streamed_actions_pass = bool(result["local_cells"]) and all(
        cell["all_mode_growth_diagnostics_pass"] for cell in result["local_cells"]
    )
    result["qualification"] = {
        "all_real_local_closures_pass": bool(local_closures_pass),
        "all_streamed_mode_closures_and_finite_checks_pass": bool(streamed_actions_pass),
        "status_requires_both": True,
    }
    result["status"] = (
        "MEASURED_BOUNDED_LOCAL_BLOCK_AND_SYNTHETIC_MODE_ACTIONS"
        if local_closures_pass and streamed_actions_pass
        else "LOCAL_OR_STREAMED_ACTION_DIAGNOSTIC_FAILED"
    )
    result["resource_scope"] = {
        "batch_size_fixed": int(args.batch_size),
        "selected_real_cells": len(result["local_cells"]),
        "global_condensation_matrix_or_factor": False,
        "mode_square_oracle": False,
        "high_mode_synthetic_stress_allocated_full_mode_square": False,
        "process_peak_rss_bytes": _process_peak_rss_bytes(),
        "process_peak_rss_method": "Linux getrusage(RUSAGE_SELF).ru_maxrss converted from KiB; includes setup and all local-cell work",
        "task_swap_bytes": "not independently sampled by this bounded component script",
        "elapsed_wall_seconds": float(time.perf_counter() - campaign_start),
        "process_cpu_seconds": float(time.process_time()),
        "p6_p4_global_factor": "not built; risk remains separately governed by measured Task40 global p4/MUMPS evidence",
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode-sizes", type=lambda text: [int(x) for x in text.split(",")], default=[80, 340, 3904])
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--bank-modes", type=int, default=80)
    parser.add_argument("--max-tags", type=int, default=3)
    parser.add_argument("--seed", type=int, default=40072026)
    args = parser.parse_args()
    result = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".partial")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(json.dumps({
        "status": result["status"],
        "output": str(args.output),
        "elapsed_wall_seconds": result["resource_scope"]["elapsed_wall_seconds"],
        "process_peak_rss_bytes": result["resource_scope"]["process_peak_rss_bytes"],
    }, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
