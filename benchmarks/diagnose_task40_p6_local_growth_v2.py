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
) -> list[dict[str, Any]]:
    ni, nt = Aii.shape[0], Ait.shape[1]
    bank_modes = int(bank["Bi"].shape[1])
    bank_bytes = _backing_inventory(list(bank.values()))["unique_backing_bytes"]
    rng = np.random.default_rng(seed + 1)
    output: list[dict[str, Any]] = []
    for mode_count in mode_sizes:
        wall_start = time.perf_counter()
        cpu_start = time.process_time()
        generation_seconds = 0.0
        reduction_seconds = 0.0
        action_seconds = 0.0
        recovery_seconds = 0.0
        max_live_bytes = 0
        max_live_backings = 0
        max_batch_columns = 0
        max_recovery_closure = 0.0
        action_norm_sums = {"trace_from_port": 0.0, "port_from_trace": 0.0, "port_feedback": 0.0}
        solved_columns = 0
        schur_column_pairs = 0
        generated_coefficients = 0
        for start in range(0, mode_count, batch_size):
            stop = min(start + batch_size, mode_count)
            k = stop - start
            max_batch_columns = max(max_batch_columns, k)
            gen_start = time.perf_counter()
            indices = np.arange(start, stop, dtype=np.int64) % bank_modes
            cycles = np.arange(start, stop, dtype=np.int64) // bank_modes
            multiplier = (1.0 + 0.01 * cycles) * np.exp(0.13j * cycles)
            Bi = _select_columns(bank["Bi"], indices, multiplier)
            Bt = _select_columns(bank["Bt"], indices, multiplier)
            trace_modes = _select_columns(bank["trace_modes"], indices, multiplier)
            Di = _select_rows(bank["Di"], indices, multiplier)
            Dt = _select_rows(bank["Dt"], indices, multiplier)
            generation_seconds += time.perf_counter() - gen_start

            reduction_start = time.perf_counter()
            XiB = lu_solve(factor, Bi, check_finite=False)
            Bhat = Bt - Ati @ XiB
            Dhat = Dt - Di @ Xit
            Hcorr = Di @ XiB
            reduction_seconds += time.perf_counter() - reduction_start

            action_start = time.perf_counter()
            alpha = _complex_random(rng, (k,), 1)
            trace_from_port = Bhat @ alpha
            trace_for_action = trace_modes @ alpha
            port_from_trace = Dhat @ trace_for_action
            port_feedback = Hcorr @ alpha
            action_norm_sums["trace_from_port"] += float(np.linalg.norm(trace_from_port))
            action_norm_sums["port_from_trace"] += float(np.linalg.norm(port_from_trace))
            action_norm_sums["port_feedback"] += float(np.linalg.norm(port_feedback))
            action_seconds += time.perf_counter() - action_start

            recovery_start = time.perf_counter()
            local_load = Ait @ trace_modes + Bi
            recovered = lu_solve(factor, -local_load, check_finite=False)
            closure_matrix = Aii @ recovered + local_load
            per_column_denominator = np.maximum(
                np.linalg.norm(local_load, axis=0), np.finfo(float).tiny
            )
            closure = np.linalg.norm(closure_matrix, axis=0) / per_column_denominator
            max_recovery_closure = max(max_recovery_closure, float(np.max(closure)))
            recovery_seconds += time.perf_counter() - recovery_start
            solved_columns += k
            schur_column_pairs += k * k
            generated_coefficients += int(Bi.size + Di.size + Bt.size + Dt.size + trace_modes.size)

            live = _backing_inventory(
                [Aii, Ait, Ati, Xit, factor[0], factor[1], *bank.values(),
                 Bi, Bt, trace_modes, Di, Dt, XiB, Bhat, Dhat, Hcorr,
                 alpha, trace_from_port, trace_for_action, port_from_trace,
                 port_feedback, local_load, recovered, closure_matrix, closure]
            )
            max_live_bytes = max(max_live_bytes, live["unique_backing_bytes"])
            max_live_backings = max(max_live_backings, live["unique_backings"])
            if Hcorr.shape != (k, k):
                raise RuntimeError("bounded port feedback block changed shape")
            if mode_count >= 3904 and Hcorr.shape[0] > batch_size:
                raise RuntimeError("high-mode stress exceeded the fixed square scratch bound")
            del Bi, Bt, trace_modes, Di, Dt, XiB, Bhat, Dhat, Hcorr
            del alpha, trace_from_port, trace_for_action, port_from_trace, port_feedback
            del local_load, recovered, closure_matrix, closure, per_column_denominator
        wall_seconds = time.perf_counter() - wall_start
        cpu_seconds = time.process_time() - cpu_start
        output.append({
            "mode_count": int(mode_count),
            "classification": "MEASURED_SYNTHETIC_RESAMPLED_CHANNEL_STRESS",
            "physical_model": False,
            "bank_mode_count": bank_modes,
            "resampling": "cycle modulo 80 with common per-column complex phase and 1% per-cycle amplitude ramp",
            "fixed_column_batch": int(batch_size),
            "batch_count": int(math.ceil(mode_count / batch_size)),
            "max_batch_columns": int(max_batch_columns),
            "processed_mode_columns": int(solved_columns),
            "stream_generated_complex_coefficients": int(generated_coefficients),
            "bounded_schur_feedback_column_pairs": int(schur_column_pairs),
            "no_mode_square_allocation": True,
            "largest_square_scratch_shape": [int(max_batch_columns), int(max_batch_columns)],
            "largest_square_scratch_bytes": int(16 * max_batch_columns * max_batch_columns),
            "base_bank_unique_backing_bytes": int(bank_bytes),
            "peak_known_live_numpy_backing_bytes": int(max_live_bytes),
            "peak_known_live_numpy_backing_count": int(max_live_backings),
            "wall_seconds": float(wall_seconds),
            "process_cpu_seconds": float(cpu_seconds),
            "process_cpu_to_wall_ratio": float(cpu_seconds / max(wall_seconds, np.finfo(float).tiny)),
            "generation_seconds": float(generation_seconds),
            "local_reduction_seconds": float(reduction_seconds),
            "action_seconds": float(action_seconds),
            "recovery_seconds": float(recovery_seconds),
            "max_nonzero_rhs_local_recovery_relative_closure": float(max_recovery_closure),
            "action_norm_sums": action_norm_sums,
            "local_dimensions": {"interior": ni, "trace": nt},
        })
        print(
            f"P6_MODE_STRESS tag-cell mode_count={mode_count} batches={output[-1]['batch_count']} "
            f"wall={wall_seconds:.3f}s cpu={cpu_seconds:.3f}s "
            f"closure={max_recovery_closure:.3e}", flush=True,
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
        )
        result["local_cells"].append(cell_record)
        print(
            f"P6_LOCAL_CELL tag={tag} cell={cell} closure={local_closure:.3e} "
            f"assemble={assembly_seconds:.3f}s factor={factor_seconds:.3f}s",
            flush=True,
        )
        del bank, native, Aii, Ait, Ati, Att, factor, Xit, schur
        del trace_rhs, interior_rhs, local_rhs, recovered, residual
    result["status"] = (
        "MEASURED_BOUNDED_LOCAL_BLOCK_AND_SYNTHETIC_MODE_ACTIONS"
        if all(cell["local_closure_pass"] for cell in result["local_cells"])
        else "LOCAL_BLOCK_CLOSURE_FAILED"
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
