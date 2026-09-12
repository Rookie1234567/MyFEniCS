"""Small M1 controls for the Review V10 physical macro inverse.

The runner deliberately owns only orchestration and evidence.  The local
operator, bounded I4 policy, transfers, and metrics remain in the reusable
solver modules.  Frozen G0 packets are read through the existing audited
loader; no reference operator or solve is rebuilt here.
"""

from __future__ import annotations

import hashlib
import gc
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np


def _array_summary(value: Any) -> dict[str, Any]:
    array = np.ascontiguousarray(np.asarray(value))
    return {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "norm": float(np.linalg.norm(array)),
        "sha256": hashlib.sha256(array.tobytes()).hexdigest(),
    }


def _mapping_identity_sha256(packet: dict[str, Any]) -> str:
    """Hash every array in a saved native-map packet with its identity."""
    facts = {
        name: _array_summary(value)
        for name, value in sorted(packet.items())
        if isinstance(value, np.ndarray)
    }
    return hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _relative(value: Any, reference: Any) -> float:
    value = np.asarray(value)
    reference = np.asarray(reference)
    return float(np.linalg.norm(value - reference) /
                 max(np.linalg.norm(reference), np.finfo(float).tiny))


def _operation_relative(value: Any, reference: Any, *scale_terms: Any) -> float:
    """Relative discrepancy scaled by the complete operation, not cancellation."""
    scale = sum(float(np.linalg.norm(np.asarray(term))) for term in scale_terms)
    return float(
        np.linalg.norm(np.asarray(value) - np.asarray(reference))
        / max(scale, np.finfo(float).tiny)
    )


def _set_full(vector: Any, values: Any, *, name: str) -> None:
    array = np.asarray(values, dtype=np.complex128)
    if array.shape != vector.array.shape or not np.isfinite(array).all():
        raise ValueError(f"{name} does not match the current full vector")
    vector.array[:] = array


def _set_independent(vector: Any, values: Any, indices: np.ndarray, *, name: str) -> None:
    array = np.asarray(values, dtype=np.complex128)
    if array.shape != indices.shape or not np.isfinite(array).all():
        raise ValueError(f"{name} does not match the current independent map")
    vector.set(0)
    vector.array[indices] = array


def _full_from_independent(
    size: int, indices: np.ndarray, values: Any,
) -> np.ndarray:
    """Materialize one full constrained vector from independent p4 rows."""
    result = np.zeros(int(size), dtype=np.complex128)
    result[np.asarray(indices, dtype=np.int64)] = np.asarray(
        values, dtype=np.complex128,
    )
    return result


def _destroy(*values: Any) -> None:
    for value in values:
        if value is not None and hasattr(value, "destroy"):
            value.destroy()


def _metric_pair(metric: Any, error: np.ndarray, reference: np.ndarray) -> dict[str, Any]:
    from src.solvers.physical_error_diagnostics import metric_square

    result: dict[str, Any] = {}
    for name, action in (("L2", metric.mass), ("scaled_curl", metric.curl)):
        error_squared = metric_square(action, error)
        reference_squared = metric_square(action, reference)
        result[name] = {
            "error_squared": error_squared,
            "reference_squared": reference_squared,
            "error_norm": float(np.sqrt(error_squared)),
            "reference_norm": float(np.sqrt(reference_squared)),
            "common_input_norm": float(np.sqrt(reference_squared)),
            "relative": float(np.sqrt(error_squared / reference_squared))
            if reference_squared > 0 else None,
        }
    return result


def _geo_mean(values: list[float]) -> float | None:
    if not values:
        return None
    values = np.maximum(np.asarray(values, dtype=np.float64), 1.0e-12)
    return float(np.exp(np.mean(np.log(values))))


def _safe_ratio(
    numerator: float | None,
    denominator: float | None,
    *,
    common_scale: float | None = None,
) -> tuple[float | None, bool]:
    if numerator is None or denominator is None:
        return None, False
    if common_scale is not None:
        scale = max(abs(float(common_scale)), np.finfo(float).tiny)
        near_zero = (
            abs(float(numerator)) <= 1.0e-12 * scale
            or abs(float(denominator)) <= 1.0e-12 * scale
        )
        if near_zero:
            return None, True
        return float(numerator / denominator), False
    near_zero = abs(float(denominator)) <= np.finfo(float).tiny
    return (None, True) if near_zero else (float(numerator / denominator), False)


def _make_scoped_save(save: Callable[[str, Any], Any], label: list[str]):
    def scoped(name: str, facts: Any) -> Any:
        return save(f"{label[0]}_{name}", facts)

    return scoped


def _calibration_backend_snapshot(factor: Any, *, phase: str) -> dict[str, Any]:
    """Capture public MUMPS controls and raw fields around repeated solves.

    ``numeric_raw`` in ``factor.audit`` is the post-numeric record.  These
    separate snapshots deliberately keep the later INFO/RINFO readback from
    being mistaken for the numeric warning record.
    """
    backend = getattr(factor, "factor", None)
    if backend is None:
        raise RuntimeError("N1 calibration backend snapshot requires a live factor")
    return {
        "phase": phase,
        "symbolic_memory_settings": backend.symbolic_memory_settings(),
        "refinement_settings": backend.refinement_settings(),
        "raw_backend_fields": backend.info(
            extra_indices=(21, 22, 29), include_local=True,
        ),
        "numeric_calls": int(backend.numeric_calls),
        "solve_calls": int(backend.solve_calls),
    }


def _calibration_solve_probe(
    matrix: Any,
    factor: Any,
    *,
    block_index: int,
    policy: str,
) -> dict[str, Any]:
    """Run one fixed RHS plus repeated solves, retaining compact vectors."""
    rhs = matrix.createVecRight()
    checked = matrix.createVecRight()
    seed_value = 390391 + 17 * int(block_index)
    rng = np.random.default_rng(seed_value)
    real = rng.standard_normal(int(matrix.getSize()[0]))
    imag = rng.standard_normal(int(matrix.getSize()[0]))
    rhs.array[:] = real + 1j * imag
    source = np.array(rhs.array, copy=True)
    rhs_sha256 = hashlib.sha256(np.ascontiguousarray(source).tobytes()).hexdigest()
    solutions = []
    timings = []
    residuals = []
    try:
        for repetition in range(4):
            started = time.perf_counter()
            solution, solve_facts = factor.solve_lean(rhs)
            elapsed = time.perf_counter() - started
            try:
                matrix.mult(solution, checked)
                checked.axpy(-1.0, rhs)
                residual = float(checked.norm() / max(rhs.norm(), np.finfo(float).tiny))
                if not np.isfinite(residual) or residual > 1.0e-10:
                    raise ValueError(
                        f"block {block_index} {policy} calibration residual {residual} exceeds 1e-10"
                    )
                residuals.append(residual)
                timings.append(elapsed)
                if repetition in (0, 3):
                    solutions.append(np.array(solution.array, copy=True))
            finally:
                solution.destroy()
        return {
            "block_index": int(block_index),
            "policy": policy,
            "rhs_values": source,
            "solution_first_values": solutions[0],
            "solution_last_values": solutions[-1],
            "solve_count_added": 4,
            "solve_timings_seconds": timings,
            "fixed_seed": int(seed_value),
            "rhs_sha256": rhs_sha256,
            "calibration_seed_solve_seconds": timings[0],
            "hot_solve_seconds": timings[1:],
            "relative_residuals": residuals,
            "max_relative_residual": max(residuals),
            "solution_repeat_difference": float(
                np.linalg.norm(solutions[-1] - solutions[0]) /
                max(np.linalg.norm(solutions[0]), np.finfo(float).tiny)
            ),
            "solution_repeat_difference_absolute": float(
                np.linalg.norm(solutions[-1] - solutions[0])
            ),
            "solve_facts": solve_facts,
        }
    finally:
        checked.destroy()
        rhs.destroy()


def run_macro_n1_calibration(
    cfg: Any,
    comm: Any,
    directory: str | Path,
    *,
    sample: Callable[[], Any],
    marker: Callable[[str, Any], Any],
    source_sha: str | None = None,
    input_path: str | Path | None = None,
    model_identity: dict[str, Any] | None = None,
    calibration_seconds: float = 900.0,
) -> dict[str, Any]:
    """Compare one old/new factor per canonical representative block.

    This is the bounded V11 N1 stage.  It uses the production local assembly
    but deliberately does not build a global p4 reference, p2 factor, or
    outer framework.  Old factors are fully released before the V11 factors
    are constructed.
    """
    from src.io.physical_recursive_profile import MACRO_V11_PROFILE
    from src.solvers.fullspace_bounded_mumps import (
        LEGACY_LOCAL_MUMPS_MEMORY_POLICY,
        SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
    )
    from src.solvers.physical_macro_dd4 import (
        build_macro_calibration_context,
        destroy_macro_stack,
    )
    from .physical_diagnosis_worker import save_packet

    if comm.size != 1:
        raise ValueError("V11 N1 calibration is MPI1-only")
    started = time.perf_counter()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)

    def save(name, facts):
        save_packet(directory, name, facts)

    model_facts = dict(model_identity or {})
    summary: dict[str, Any] = {
        "schema": "task39extra.review-v11.n1-calibration.v1",
        "status": "N1_STARTED",
        "profile": MACRO_V11_PROFILE,
        "source_sha": source_sha,
        "input_path": str(Path(input_path).resolve()) if input_path is not None else None,
        "model_identity": model_facts,
        "policies": [
            LEGACY_LOCAL_MUMPS_MEMORY_POLICY,
            SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
        ],
        "representative_blocks": [],
        "old": [],
        "new": [],
        "comparisons": [],
        "numeric_factorizations": 0,
        "numeric_attempts": {"old": 0, "new": 0},
        "max_solves_per_factor": 0,
        "context_reused_for_n2": False,
        "n2_context_mode": "fresh_process_rebuild_required",
        "stage_times": {"build": None, "old": None, "new": None, "total": None},
        "last_safe_stage": None,
    }
    context: dict[str, Any] | None = None
    active_strategy: str | None = None

    def calibration_marker(name: str, facts: Any) -> None:
        if name in ("p1_numeric_started", "p2_numeric_started") and active_strategy is not None:
            summary["numeric_attempts"][active_strategy] += 1
        marker(name, facts)

    def checkpoint(stage: str) -> None:
        summary["last_safe_stage"] = stage
        sample()
        if time.perf_counter() - started > calibration_seconds:
            raise TimeoutError(
                f"N1 calibration budget exceeded after {stage}: "
                f"{time.perf_counter() - started:.6f}s"
            )

    try:
        marker("macro_n1_context_started", {"profile": MACRO_V11_PROFILE})
        context = build_macro_calibration_context(
            cfg, comm, sample=sample, marker=calibration_marker, save=save,
            memory_policy=SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
        )
        local = context["local"]
        dtn4 = context["dtn4"]
        native_a4 = context["native_a4"]
        selected_by_category = local._select_representative_blocks(dtn4.carrier)
        selected = sorted(set(selected_by_category.values()))
        if not 1 <= len(selected) <= 3:
            raise ValueError(f"V11 N1 representative count is {len(selected)}, expected 1..3")
        summary["representative_selection"] = {
            "by_category": {key: int(value) for key, value in selected_by_category.items()},
            "selected_blocks": selected,
            "selection_notes": dict(getattr(local, "representative_selection_notes", {})),
        }
        summary["representative_blocks"] = [
            {
                "block_index": int(index),
                "seed": list(local.blocks[index]["seed"]),
                "rows": int(np.asarray(local.blocks[index]["indices"]).size),
                "support_cells": list(local.blocks[index]["support_cells"]),
            }
            for index in selected
        ]
        save("n1_representative_selection", summary["representative_selection"])
        checkpoint("representatives_frozen")
        summary["stage_times"]["build"] = time.perf_counter() - started

        old_records: dict[int, dict[str, Any]] = {}
        old_save = _make_scoped_save(save, ["old"])
        old_started = time.perf_counter()
        active_strategy = "old"
        local.add_dtn_terms(
            dtn4.carrier, native_a4=native_a4, save=old_save,
            block_indices=selected, memory_policy=LEGACY_LOCAL_MUMPS_MEMORY_POLICY,
        )
        for index in selected:
            block = local.blocks[index]
            factor = block["factor"]
            backend_before = _calibration_backend_snapshot(
                factor, phase="after_two_Dw_before_seed_repeats",
            )
            if backend_before["solve_calls"] != 2:
                raise RuntimeError(
                    f"N1 backend sample order invalid before seed repeats: "
                    f"expected solve_calls=2, got {backend_before['solve_calls']}"
                )
            probe = _calibration_solve_probe(
                block["matrix"], factor, block_index=index,
                policy=LEGACY_LOCAL_MUMPS_MEMORY_POLICY,
            )
            # The probe has already completed its four repeated solves.  Keep
            # this second raw read separate from factor.audit.numeric_raw.
            backend_after = _calibration_backend_snapshot(
                factor, phase="after_four_repeated_solves",
            )
            if backend_after["solve_calls"] != 6:
                raise RuntimeError(
                    f"N1 backend sample order invalid after seed repeats: "
                    f"expected solve_calls=6, got {backend_after['solve_calls']}"
                )
            record = {
                "block_index": int(index),
                "identity": dict(block["identity"]),
                "factor_audit": dict(factor.audit),
                "backsolve": block.get("backsolve"),
                "native_witness": block.get("native_witness"),
                "probe": probe,
                "backend_before_repeated_solves": backend_before,
                "backend_after_repeated_solves": backend_after,
            }
            old_records[index] = record
            summary["old"].append(record)
            summary["numeric_factorizations"] += 1
            summary["max_solves_per_factor"] = max(
                summary["max_solves_per_factor"], int(factor.solve_count)
            )
            save(f"old_block_{index:02d}_comparison", record)
            checkpoint(f"old_block_{index:02d}_complete")
        summary["stage_times"]["old"] = time.perf_counter() - old_started
        active_strategy = None
        summary["old_resource_before_release"] = sample()
        local.release_block_factors(selected)
        summary["old_resource_after_release"] = sample()
        save("old_strategy_resources", {
            "before_release": summary["old_resource_before_release"],
            "after_release": summary["old_resource_after_release"],
        })
        checkpoint("old_factors_released")

        new_save = _make_scoped_save(save, ["new"])
        new_started = time.perf_counter()
        active_strategy = "new"
        local.add_dtn_terms(
            dtn4.carrier, native_a4=native_a4, save=new_save,
            block_indices=selected, memory_policy=SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
        )
        for index in selected:
            block = local.blocks[index]
            factor = block["factor"]
            backend_before = _calibration_backend_snapshot(
                factor, phase="after_two_Dw_before_seed_repeats",
            )
            if backend_before["solve_calls"] != 2:
                raise RuntimeError(
                    f"N1 backend sample order invalid before seed repeats: "
                    f"expected solve_calls=2, got {backend_before['solve_calls']}"
                )
            probe = _calibration_solve_probe(
                block["matrix"], factor, block_index=index,
                policy=SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
            )
            backend_after = _calibration_backend_snapshot(
                factor, phase="after_four_repeated_solves",
            )
            if backend_after["solve_calls"] != 6:
                raise RuntimeError(
                    f"N1 backend sample order invalid after seed repeats: "
                    f"expected solve_calls=6, got {backend_after['solve_calls']}"
                )
            record = {
                "block_index": int(index),
                "identity": dict(block["identity"]),
                "factor_audit": dict(factor.audit),
                "backsolve": block.get("backsolve"),
                "native_witness": block.get("native_witness"),
                "probe": probe,
                "backend_before_repeated_solves": backend_before,
                "backend_after_repeated_solves": backend_after,
            }
            summary["new"].append(record)
            summary["numeric_factorizations"] += 1
            summary["max_solves_per_factor"] = max(
                summary["max_solves_per_factor"], int(factor.solve_count)
            )
            old = old_records[index]
            old_identity = old["identity"]
            new_identity = record["identity"]
            identity_equal = old_identity == new_identity
            old_solution = old["probe"]["solution_first_values"]
            new_solution = probe["solution_first_values"]
            solution_difference = float(
                np.linalg.norm(new_solution - old_solution) /
                max(np.linalg.norm(old_solution), np.finfo(float).tiny)
            )
            solution_difference_absolute = float(np.linalg.norm(new_solution - old_solution))
            comparison = {
                "block_index": int(index),
                "matrix_identity_equal": identity_equal,
                "old_csr_values_sha256": old_identity.get("csr_values_sha256"),
                "new_csr_values_sha256": new_identity.get("csr_values_sha256"),
                "old_csr_structure_sha256": old_identity.get("csr_structure_sha256"),
                "new_csr_structure_sha256": new_identity.get("csr_structure_sha256"),
                "old_max_local_residual": max(old["probe"]["relative_residuals"]),
                "new_max_local_residual": max(probe["relative_residuals"]),
                "solution_difference": solution_difference,
                "solution_difference_absolute": solution_difference_absolute,
                "solution_difference_limit": 1.0e-10,
                "local_residual_limit": 1.0e-10,
                "old_policy": LEGACY_LOCAL_MUMPS_MEMORY_POLICY,
                "new_policy": SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
            }
            comparison["gate_pass"] = bool(
                identity_equal and comparison["old_max_local_residual"] <= 1.0e-10
                and comparison["new_max_local_residual"] <= 1.0e-10
                and solution_difference <= 1.0e-10
            )
            summary["comparisons"].append(comparison)
            save(f"comparison_block_{index:02d}", comparison)
            if not comparison["gate_pass"]:
                active_strategy = None
                raise RuntimeError(f"LOCAL_NUMERICAL_EQUIVALENCE_FAIL: {comparison}")
            checkpoint(f"new_block_{index:02d}_complete")
        summary["stage_times"]["new"] = time.perf_counter() - new_started
        active_strategy = None
        summary["new_resource_before_release"] = sample()
        local.release_block_factors(selected)
        summary["new_resource_after_release"] = sample()
        save("new_strategy_resources", {
            "before_release": summary["new_resource_before_release"],
            "after_release": summary["new_resource_after_release"],
        })
        checkpoint("new_factors_released")
        summary["stage_times"]["total"] = time.perf_counter() - started
        summary.update(status="N1_CALIBRATION_COMPLETED", gate_pass=True)
        save("n1_summary", summary)
        return summary
    except BaseException as exc:
        summary["stage_times"]["total"] = time.perf_counter() - started
        summary.update(
            status="N1_CALIBRATION_FAILED",
            gate_pass=False,
            exception_type=type(exc).__name__,
            exception=str(exc),
        )
        save("n1_summary", summary)
        raise
    finally:
        if context is not None:
            destroy_macro_stack(context)


def _stack_cost_snapshot(stack: dict[str, Any], i4: Any) -> dict[str, Any]:
    """Read the fixed V10 counters into one flat, hashable snapshot.

    These interfaces are part of the qualified macro stack.  Missing fields
    are an implementation error, not a reason to emit a partial generic
    serialization of the whole audit/configuration tree.
    """
    local = stack["local"]
    additive = stack["additive"]
    b4 = stack["B4"]
    h6 = stack["positive"]["h6"]
    transfer = local.transfer
    p64_transfer = stack["actions"]["transfers"][(6, 4)]
    b4_counts = b4.total_counts
    b4_seconds = b4.total_operation_seconds
    p2_counts = stack["p2_inverse"].counts
    cached_counts = stack["a4"].counts
    native_apply = stack["a4_native"].audit["apply_count"]
    a6_apply = stack["a6"].audit["apply_count"]
    return {
        "I4_calls": int(i4.calls),
        "B4_calls": int(b4.apply_count),
        "B4_C": int(b4_counts["C"]),
        "B4_smoother": int(b4_counts["smoother"]),
        "B4_A_structure": int(b4_counts["A_structure"]),
        "B4_A_inner_true": int(b4_counts["A_inner_true"]),
        "B4_PH_audit": int(b4_counts["PH_audit"]),
        "B4_C_seconds": float(b4_seconds["C"]),
        "B4_smoother_seconds": float(b4_seconds["smoother"]),
        "B4_A_structure_seconds": float(b4_seconds["A_structure"]),
        "B4_A_inner_true_seconds": float(b4_seconds["A_inner_true"]),
        "local_internal_calls": int(stack["internal"].calls),
        "local_volume_calls": int(stack["volume"].calls),
        "MD_calls": int(additive.calls),
        "MD_local_solves": int(additive.local_solves),
        "MD_seconds": float(additive.seconds),
        "p2_logical": int(p2_counts["logical"]),
        "p2_MatSolve_attempted": int(p2_counts["MatSolve_attempted"]),
        "p2_MatSolve": int(p2_counts["MatSolve"]),
        "p2_refinement": int(p2_counts["refinement"]),
        "p2_A2_true": int(p2_counts["A2_true"]),
        "H6_apply_count": int(h6.apply_count),
        "H6_matrix_mult_count": int(h6.matrix_mult_count),
        "transfer_primal": int(transfer.primal_count),
        "transfer_adjoint": int(transfer.adjoint_count),
        "P64_primal": int(p64_transfer.primal_count),
        "P64_adjoint": int(p64_transfer.adjoint_count),
        "cached_A4_started": int(cached_counts["started"]),
        "cached_A4_completed": int(cached_counts["completed"]),
        "native_A4_apply_count": int(native_apply),
        "A6_apply_count": int(a6_apply),
    }


def _counter_delta(after: Any, before: Any) -> Any:
    if set(after) != set(before):
        raise ValueError("counter snapshots have different fixed fields")
    return {key: after[key] - before[key] for key in after}


def _seed_energy_groups(energies: dict[str, Any]) -> list[dict[str, Any]]:
    """Aggregate existing cell-energy output by the frozen 2x2x2 seed."""
    centers = np.asarray(energies["cell_centers"])
    axes = [np.unique(centers[:, axis]) for axis in range(3)]
    coordinates = [tuple(int(np.flatnonzero(axis == center[dimension])[0])
                        for dimension, axis in enumerate(axes))
                   for center in centers]
    cell_by_coordinate = {coordinate: cell for cell, coordinate in enumerate(coordinates)}
    seeds = [tuple(value // 2 for value in coordinate) for coordinate in coordinates]
    boundary = []
    for coordinate, seed in zip(coordinates, seeds, strict=True):
        touches = False
        for dimension in range(3):
            for direction in (-1, 1):
                neighbor = list(coordinate)
                neighbor[dimension] += direction
                neighbor_cell = cell_by_coordinate.get(tuple(neighbor))
                if neighbor_cell is not None and seeds[neighbor_cell] != seed:
                    touches = True
        boundary.append(touches)
    groups: dict[tuple[int, int, int], dict[str, Any]] = {}
    for cell, center in enumerate(centers):
        seed = seeds[cell]
        item = groups.setdefault(seed, {
            "seed": list(seed),
            "cells": 0,
            "material_tags": set(),
            "mass": 0.0,
            "curl": 0.0,
            "boundary_cells": 0,
            "boundary_mass": 0.0,
            "boundary_curl": 0.0,
        })
        item["cells"] += 1
        item["material_tags"].add(int(energies["material_tags"][cell]))
        item["mass"] += float(energies["mass"][cell])
        item["curl"] += float(energies["curl"][cell])
        if boundary[cell]:
            item["boundary_cells"] += 1
            item["boundary_mass"] += float(energies["mass"][cell])
            item["boundary_curl"] += float(energies["curl"][cell])
    result = []
    for _, item in sorted(groups.items()):
        item = dict(item, material_tags=sorted(item["material_tags"]))
        item["boundary_fraction"] = item["boundary_cells"] / item["cells"]
        item["boundary_resolution"] = (
            "all_cells_touch_seed_boundary"
            if item["boundary_cells"] == item["cells"]
            else "cellwise_boundary_band"
        )
        result.append(item)
    return result


def run_macro_m1_controls(
    cfg: Any,
    comm: Any,
    inventory_path: str | Path,
    directory: str | Path,
    *,
    sample: Callable[[], Any],
    marker: Callable[[str, Any], Any],
    source_sha: str | None = None,
    input_path: str | Path | None = None,
    model_identity: dict[str, Any] | None = None,
    build_started: float | None = None,
    profile: str | None = None,
    memory_policy: str | None = None,
) -> dict[str, Any]:
    """Run the bounded M1 controls on one shared macro stack.

    There are six independent p4 calibration I4 calls.  The three matched
    p6 ``e/q`` controls then reuse that same stack and share the first
    ``z_c`` and ``s`` operations; BAL_H alone performs the second ``t`` I4.
    Thus the shared framework comparison adds exactly six I4 calls at most.
    """

    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.fullspace_physical_intermediate_runtime import level_vector
    from src.solvers.physical_error_metric import LosslessFEMetric
    from src.solvers.physical_inexact_balance import InexactBalanceLedger
    from src.solvers.physical_macro_dd4 import (
        MacroI4,
        build_macro_stack,
        destroy_macro_stack,
    )
    from src.io.physical_recursive_profile import (
        MACRO_V10_PROFILE, MACRO_V11_PROFILE, MACRO_V12_PROFILE,
    )
    from src.solvers.fullspace_bounded_mumps import (
        LEGACY_LOCAL_MUMPS_MEMORY_POLICY,
        SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
    )

    active_profile = profile or MACRO_V10_PROFILE
    active_memory_policy = memory_policy or (
        SYMBOLIC_SIZED_LOCAL_MUMPS_V11 if active_profile in (MACRO_V11_PROFILE, MACRO_V12_PROFILE)
        else LEGACY_LOCAL_MUMPS_MEMORY_POLICY
    )
    if (active_profile, active_memory_policy) not in (
        (MACRO_V10_PROFILE, LEGACY_LOCAL_MUMPS_MEMORY_POLICY),
        (MACRO_V11_PROFILE, SYMBOLIC_SIZED_LOCAL_MUMPS_V11),
        (MACRO_V12_PROFILE, SYMBOLIC_SIZED_LOCAL_MUMPS_V11),
    ):
        raise ValueError("macro profile and memory policy are not a reviewed pair")

    from .physical_diagnosis_worker import save_packet
    from .physical_recursive_controls import (
        load_recursive_balanced_inputs,
        load_recursive_calibration,
        verify_recursive_map,
    )

    if comm.size != 1:
        raise ValueError("M1 macro controls are qualified only for MPI1")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    save = lambda name, facts: save_packet(directory, name, facts)
    label = ["m1"]
    scoped_save = _make_scoped_save(save, label)
    inventory_data = load_recursive_balanced_inputs(inventory_path)
    calibration = load_recursive_calibration(
        inventory_path, allow_missing_reference=active_profile == MACRO_V12_PROFILE,
    )
    maps = inventory_data["maps"]
    map6 = maps[6]
    map4 = maps[4]
    p6_indices = np.asarray(map6["independent_indices"], dtype=np.int64)
    p4_indices = np.asarray(map4["independent_indices"], dtype=np.int64)
    input_names = ("A2R160", "LIGHT448", "JOINT448")
    if [item["identity"]["stem"].split("_BAL_H_p4_")[0] for item in calibration[::2]] != list(input_names):
        raise ValueError("frozen six calibration order does not match the three G0 models")
    native_map_sha256 = {
        str(degree): _mapping_identity_sha256(packet)
        for degree, packet in maps.items()
    }
    model_facts = {**model_identity} if model_identity is not None else {}

    summary: dict[str, Any] = {
        "status": "M1_STARTED",
        "profile": active_profile,
        "memory_policy": active_memory_policy,
        "source_sha": source_sha,
        "input_path": str(Path(input_path).resolve()) if input_path is not None else None,
        "model_identity": model_facts,
        "inventory_path": str(Path(inventory_path).resolve()),
        "inventory_sha256": hashlib.sha256(Path(inventory_path).read_bytes()).hexdigest(),
        "e1_audit_sha256": inventory_data["e1_audit_sha256"],
        "maps": {
            "p6_independent_rows": int(p6_indices.size),
            "p4_independent_rows": int(p4_indices.size),
            "p6_sha256": hashlib.sha256(np.ascontiguousarray(p6_indices).tobytes()).hexdigest(),
            "p4_sha256": hashlib.sha256(np.ascontiguousarray(p4_indices).tobytes()).hexdigest(),
            "native_map_sha256": native_map_sha256,
        },
        "bare_calibration": [],
        "reference_status_counts": {
            "REFERENCE_AVAILABLE": 0,
            "REFERENCE_UNAVAILABLE": 0,
        },
        "shared_framework": [],
        "new_i4_calls": 0,
        "attempted_i4_calls": 0,
        "completed_i4_calls": 0,
        "bare_b4_calls": 0,
        "bare_b4_attempted_calls": 0,
        "bare_b4_completed_calls": 0,
        "outer_pc_calls": 0,
        "stage_times": {
            "build": {
                "limit_seconds": 3600.0,
                "started_by": "worker_setup" if build_started is not None else "macro_runner",
                "elapsed_seconds": None,
            },
            "controls": {
                "limit_seconds": 1200.0,
                "elapsed_seconds": None,
            },
            "budget_relation": "build_and_controls_are_inclusive_M0_M1_5400_budget",
        },
        "macro_stack_identity": None,
        "last_safe_stage": None,
    }
    stack: dict[str, Any] | None = None
    metric4 = metric6 = None
    i4: MacroI4 | None = None
    bal_ledger = one_ledger = None
    build_start = time.perf_counter() if build_started is None else build_started
    controls_start: float | None = None

    def control_checkpoint(stage: str) -> None:
        summary["last_safe_stage"] = stage
        if controls_start is None:
            return
        elapsed = time.perf_counter() - controls_start
        summary["stage_times"]["controls"]["elapsed_seconds"] = elapsed
        if elapsed > 1200.0:
            raise TimeoutError(
                f"M1 finite-control budget exceeded after {stage}: {elapsed:.6f}s"
            )

    def budget_sample() -> Any:
        """Use the existing resource checkpoint as the stage safe point."""
        resource = sample()
        summary["last_safe_stage"] = "resource_sample"
        now = time.perf_counter()
        if controls_start is None:
            elapsed = now - build_start
            if elapsed > 3600.0:
                summary["stage_times"]["build"]["elapsed_seconds"] = elapsed
                save("stage_budget_overrun", {
                    "stage": "build",
                    "elapsed_seconds": elapsed,
                    "limit_seconds": 3600.0,
                    "resource": resource,
                })
                raise TimeoutError(
                    f"M1 local construction budget exceeded at a safe point: {elapsed:.6f}s"
                )
        else:
            elapsed = now - controls_start
            summary["stage_times"]["controls"]["elapsed_seconds"] = elapsed
            if elapsed > 1200.0:
                save("stage_budget_overrun", {
                    "stage": "controls",
                    "elapsed_seconds": elapsed,
                    "limit_seconds": 1200.0,
                    "resource": resource,
                })
                raise TimeoutError(
                    f"M1 finite-control budget exceeded at a safe point: {elapsed:.6f}s"
                )
        return resource

    def stop_requested() -> bool:
        return controls_start is not None and time.perf_counter() - controls_start >= 1200.0

    try:
        marker("macro_m1_inventory_loaded", {
            "calibration_rhs": len(calibration),
            "shared_inputs": list(input_names),
            "e1_audit_sha256": inventory_data["e1_audit_sha256"],
        })
        stack = build_macro_stack(
            cfg, comm, sample=budget_sample, marker=marker, save=save,
            memory_policy=active_memory_policy,
            local_inventory_cap_bytes=(2684354560 if active_profile == MACRO_V12_PROFILE
                                       else 2147483648),
        )
        verify_recursive_map(stack, 6, map6)
        verify_recursive_map(stack, 4, map4)
        stack_identity = {
            "profile": active_profile,
            "memory_policy": active_memory_policy,
            "mode_sha256": stack["mode_sha256"],
            "p4_bridge": stack["a4_bridge"],
            "p2_matrix": stack["p2_matrix_facts"],
            "coverage": stack["local"].coverage,
            "resident_bytes": stack["local"].resident_bytes,
            "new_reference_factor": False,
            "p4_global_matrix": False,
            "p4_global_factor": False,
        }
        save("macro_stack_identity", stack_identity)
        stack_identity_path = Path(directory) / "macro_stack_identity.json"
        summary["macro_stack_identity"] = {
            "path": str(stack_identity_path),
            "sha256": hashlib.sha256(stack_identity_path.read_bytes()).hexdigest(),
            "mode_sha256": stack["mode_sha256"],
        }
        model_facts.update(
            mode_sha256=stack["mode_sha256"],
            native_map_sha256=native_map_sha256,
        )
        i4 = MacroI4(
            stack["a4"], stack["a4_native"], stack["B4"],
            sample=budget_sample, save=scoped_save, stop_requested=stop_requested,
        )
        build_seconds = time.perf_counter() - build_start
        summary["stage_times"]["build"]["elapsed_seconds"] = build_seconds
        if build_seconds > 3600.0:
            raise TimeoutError(
                f"M1 local construction budget exceeded: {build_seconds:.6f}s"
            )
        controls_start = time.perf_counter()
        summary["stage_times"]["controls"]["started_by"] = "after_macro_stack"

        # The six p4 controls are deliberately bare: one explicit B4 action
        # and one final bounded I4 per frozen RHS, without an outer PC call.
        metric4 = LosslessFEMetric(
            stack["levels"], 4, cfg.k0,
            stack["actions"]["volume_quadrature_metadata"],
        )
        for ordinal, item in enumerate(calibration, start=1):
            stem = item["identity"]["stem"]
            label[0] = f"bare_{stem}"
            rhs = level_vector(stack["levels"], 4)
            bare = bare_a = bare_error = result = error = error_a = None
            reference = reference_a = None
            source_before = None
            reference_available = bool(item.get("reference_available", False))
            reference_status = item.get(
                "reference_status",
                "REFERENCE_AVAILABLE" if reference_available else "REFERENCE_UNAVAILABLE",
            )
            summary["reference_status_counts"][reference_status] = (
                summary["reference_status_counts"].get(reference_status, 0) + 1
            )
            try:
                _set_full(rhs, item["rhs"], name=f"{stem} RHS")
                source_before = rhs.array.copy()
                cost_before = _stack_cost_snapshot(stack, i4)
                started = time.perf_counter()
                summary["bare_b4_attempted_calls"] += 1
                bare = stack["B4"].apply(rhs)
                bare_seconds = time.perf_counter() - started
                bare_a = apply_owned(stack["a4_native"], bare)
                bare_eps = rhs.array - bare_a.array
                summary["bare_b4_calls"] += 1
                summary["bare_b4_completed_calls"] += 1
                reference_residual = None
                reference_bridge = None
                reference_bridge_scale = None
                if reference_available:
                    reference_residual = rhs.array - item["reference_A4y"]
                    reference = rhs.duplicate()
                    reference.array[:] = item["reference_y"]
                    reference_a = apply_owned(stack["a4_native"], reference)
                    reference_bridge_scale = max(
                        np.linalg.norm(reference_a.array) + np.linalg.norm(item["reference_A4y"]),
                        np.finfo(float).tiny,
                    )
                    reference_bridge = float(
                        np.linalg.norm(reference_a.array - item["reference_A4y"])
                        / reference_bridge_scale
                    )
                result = i4.apply(rhs)
                summary["new_i4_calls"] += 1
                summary["attempted_i4_calls"] = i4.calls
                summary["completed_i4_calls"] = summary["new_i4_calls"]
                field = bare_field = cell_energies = None
                identity = identity_raw_norm = identity_scale = None
                if reference_available:
                    bare_error = rhs.duplicate()
                    bare_error.array[:] = item["reference_y"] - bare.array
                    error = rhs.duplicate()
                    error.array[:] = item["reference_y"] - result["solution"].array
                    error_a = apply_owned(stack["a4_native"], error)
                    identity_rhs = result["residual"].array - reference_residual
                    identity_raw_norm = float(np.linalg.norm(error_a.array - identity_rhs))
                    identity_scale = max(
                        np.linalg.norm(reference_a.array)
                        + np.linalg.norm(result["applied"].array)
                        + np.linalg.norm(rhs.array),
                        np.finfo(float).tiny,
                    )
                    identity = float(identity_raw_norm / identity_scale)
                    evaluation_started = time.perf_counter()
                    field = _metric_pair(
                        metric4,
                        error.array[p4_indices],
                        item["reference_y"][p4_indices],
                    )
                    bare_field = _metric_pair(
                        metric4,
                        bare_error.array[p4_indices],
                        item["reference_y"][p4_indices],
                    )
                    cell_energies = metric4.cell_energies(
                        error.array[p4_indices], checkpoint=budget_sample,
                    )
                    evaluation_seconds = time.perf_counter() - evaluation_started
                else:
                    evaluation_seconds = 0.0
                rho = float(np.linalg.norm(result["residual"].array) /
                            max(np.linalg.norm(rhs.array), np.finfo(float).tiny))
                r_ref = (float(np.linalg.norm(reference_residual) /
                               max(np.linalg.norm(rhs.array), np.finfo(float).tiny))
                         if reference_residual is not None else None)
                cost_after = _stack_cost_snapshot(stack, i4)
                facts = {
                    "ordinal": ordinal,
                    "stem": stem,
                    "rhs": _array_summary(rhs.array),
                    "bare_B4": {
                        "seconds": bare_seconds,
                        "applied": _array_summary(bare.array),
                        "field": bare_field,
                        "true_residual_ratio": float(np.linalg.norm(bare_eps) /
                                                      max(np.linalg.norm(rhs.array), np.finfo(float).tiny)),
                    },
                    "I4": dict(result["facts"]),
                    "I4_solution": _array_summary(result["solution"].array),
                    "I4_true_residual_ratio": rho,
                    "reference_residual_ratio": r_ref,
                    "reference_A4y_bridge_relative": reference_bridge,
                    "reference_A4y_bridge_scale": reference_bridge_scale,
                    "A4_error_identity_relative": identity,
                    "A4_error_identity_raw_norm": identity_raw_norm,
                    "A4_error_identity_scale": identity_scale,
                    "A4_error_identity_limit": 1.0e-10,
                    "field": field,
                    "cell_energies": ({
                        "I4_error": cell_energies,
                        "patch_groups": _seed_energy_groups(cell_energies),
                    } if cell_energies is not None else {
                        "status": "REFERENCE_UNAVAILABLE",
                    }),
                    "evaluation_seconds": evaluation_seconds,
                    "cost": {
                        "start": cost_before,
                        "end": cost_after,
                        "delta": _counter_delta(cost_after, cost_before),
                    },
                    # Required ignored evidence for an independent checker;
                    # save_packet compacts these into one hash-bound NPZ.
                    "rhs_values": rhs.array.copy(),
                    "reference_values": (reference.array.copy()
                                         if reference is not None else None),
                    "reference_A4y_values": (np.array(item["reference_A4y"], copy=True)
                                             if reference_available else None),
                    "bare_solution_values": bare.array.copy(),
                    "bare_applied_values": bare_a.array.copy(),
                    "bare_residual_values": bare_eps.copy(),
                    "I4_solution_values": result["solution"].array.copy(),
                    "I4_applied_values": result["applied"].array.copy(),
                    "I4_residual_values": result["residual"].array.copy(),
                    "error_values": (error.array.copy() if error is not None else None),
                    "A4_error_values": (error_a.array.copy() if error_a is not None else None),
                    "reference_residual_values": (reference_residual.copy()
                                                   if reference_residual is not None else None),
                    "input_unchanged": bool(np.array_equal(rhs.array, source_before)),
                    "reference_role": "measurement_only" if reference_available else "REFERENCE_UNAVAILABLE",
                    "reference_status": reference_status,
                }
                save(f"{stem}_bare_B4_I4", facts)
                if (not facts["input_unchanged"] or not np.isfinite(rho)
                        or not np.isfinite(float(np.linalg.norm(bare_eps)))
                        or (reference_available and (reference_bridge > 1.0e-10
                                                     or identity > 1.0e-10))):
                    raise ValueError(f"{stem} M1 p4 identity/input gate failed")
                summary["bare_calibration"].append({
                    "stem": stem,
                    "rho4": rho,
                    "eta4_L2": None if field is None else field["L2"]["relative"],
                    "eta4_scaled_curl": None if field is None else field["scaled_curl"]["relative"],
                    "I4_status": result["facts"].get("status"),
                    "B4_calls": result["facts"].get("B4_calls", 0),
                    "A4_error_identity_relative": identity,
                    "reference_status": reference_status,
                })
                control_checkpoint(f"bare:{stem}")
            finally:
                _destroy(reference_a, reference, error_a, error, bare_error, bare_a, bare, rhs)
                if result is not None:
                    _destroy(result.get("solution"), result.get("applied"), result.get("residual"))
        metric4.destroy()
        metric4 = None

        # Framework comparison: one stack, one first coarse correction and
        # one H6 response per q.  BAL_H adds only its second I4 feedback.
        metric6 = LosslessFEMetric(
            stack["levels"], 6, cfg.k0,
            stack["actions"]["volume_quadrature_metadata"],
        )
        transfer = stack["actions"]["transfers"][(6, 4)]
        a6 = stack["a6"]
        bal_ledger = InexactBalanceLedger(
            lambda value: apply_owned(a6, value),
            transfer.apply_adjoint,
            save=lambda name, facts: scoped_save("BAL_" + name, facts),
            checkpoint=budget_sample, every=32, mode="BAL_H",
        )
        one_ledger = InexactBalanceLedger(
            lambda value: apply_owned(a6, value),
            transfer.apply_adjoint,
            save=lambda name, facts: scoped_save("ONE_" + name, facts),
            checkpoint=budget_sample, every=32, mode="ONE_C",
        )
        for ordinal, name in enumerate(input_names, start=1):
            label[0] = f"shared_{name}"
            item = inventory_data["inputs"][name]
            q = e = ae = rhs1 = rhs2 = None
            zc = azc = rc = s = a_s = zt = z_bal = z_one = None
            az_bal = az_one = None
            result1 = result2 = None
            try:
                cost_before = _stack_cost_snapshot(stack, i4)
                q = level_vector(stack["levels"], 6)
                e = level_vector(stack["levels"], 6)
                _set_independent(q, item["q"], p6_indices, name=f"{name} q")
                _set_independent(e, item["e"], p6_indices, name=f"{name} e")
                ae = apply_owned(a6, e)
                q_bridge = _relative(ae.array[p6_indices], item["q"])
                if q_bridge > 1.0e-10:
                    save(f"{name}_shared_failed", {
                        "failure": "A6_e_q_bridge",
                        "q_bridge_relative": q_bridge,
                        "q": q.array.copy(),
                        "e": e.array.copy(),
                        "A6e": ae.array.copy(),
                        "expected_q": np.array(item["q"], copy=True),
                    })
                    raise ValueError(f"{name} frozen q is not the current A6 e")
                q_before = q.array.copy()
                shared_started = time.perf_counter()
                rhs1 = transfer.apply_adjoint(q)
                label[0] = f"shared_{name}_first"
                result1 = i4.apply(rhs1)
                summary["new_i4_calls"] += 1
                summary["attempted_i4_calls"] = i4.calls
                summary["completed_i4_calls"] = summary["new_i4_calls"]
                zc = transfer.apply_primal(result1["solution"])
                azc = apply_owned(a6, zc)
                rc = q.copy()
                rc.axpy(-1.0, azc)
                _destroy(azc)
                azc = None
                s = stack["positive"]["h6"].apply(rc)
                a_s = apply_owned(a6, s)
                rhs2 = transfer.apply_adjoint(a_s)
                z_one = zc.copy()
                z_one.axpy(1.0, s)
                shared_seconds = time.perf_counter() - shared_started
                label[0] = f"shared_{name}_second"
                second_started = time.perf_counter()
                result2 = i4.apply(rhs2)
                summary["new_i4_calls"] += 1
                summary["attempted_i4_calls"] = i4.calls
                summary["completed_i4_calls"] = summary["new_i4_calls"]
                zt = transfer.apply_primal(result2["solution"])
                z_bal = z_one.copy()
                z_bal.axpy(-1.0, zt)
                feedback_seconds = time.perf_counter() - second_started
                ledger_started = time.perf_counter()
                bal_ledger.begin()
                bal_ledger.record(rhs1, result1["applied"], result1["residual"], result1["facts"])
                bal_ledger.record(rhs2, result2["applied"], result2["residual"], result2["facts"])
                bal_summary = bal_ledger.finish(q, z_bal, ordinal + 1)
                bal_ledger_seconds = time.perf_counter() - ledger_started
                audit_started = time.perf_counter()
                bal_audit = bal_ledger.audit_last()
                bal_audit_seconds = time.perf_counter() - audit_started
                ledger_started = time.perf_counter()
                one_ledger.begin()
                one_ledger.record(rhs1, result1["applied"], result1["residual"], result1["facts"])
                one_ledger.record_g2(rhs2)
                one_summary = one_ledger.finish(q, z_one, ordinal + 1)
                one_ledger_seconds = time.perf_counter() - ledger_started
                audit_started = time.perf_counter()
                one_audit = one_ledger.audit_last()
                one_audit_seconds = time.perf_counter() - audit_started
                evaluation_started = time.perf_counter()
                az_bal = apply_owned(a6, z_bal)
                az_one = apply_owned(a6, z_one)
                e_bal = e.array[p6_indices] - z_bal.array[p6_indices]
                e_one = e.array[p6_indices] - z_one.array[p6_indices]
                field_bal = _metric_pair(metric6, e_bal, item["e"])
                field_one = _metric_pair(metric6, e_one, item["e"])
                q_norm = max(float(np.linalg.norm(item["q"])), np.finfo(float).tiny)
                residual_bal_norm = float(np.linalg.norm(item["q"] - az_bal.array[p6_indices]))
                residual_one_norm = float(np.linalg.norm(item["q"] - az_one.array[p6_indices]))
                residual_bal = residual_bal_norm / q_norm
                residual_one = residual_one_norm / q_norm
                cells_bal = metric6.cell_energies(e_bal, checkpoint=budget_sample)
                cells_one = metric6.cell_energies(e_one, checkpoint=budget_sample)
                evaluation_seconds = time.perf_counter() - evaluation_started
                cost_after = _stack_cost_snapshot(stack, i4)
                facts = {
                    "name": name,
                    "q_bridge_relative": q_bridge,
                    "q_bridge_limit": 1.0e-10,
                    "input_q": _array_summary(item["q"]),
                    "input_e": _array_summary(item["e"]),
                    "zc": _array_summary(zc.array[p6_indices]),
                    "s": _array_summary(s.array[p6_indices]),
                    "t": _array_summary(zt.array[p6_indices]),
                    "q_values": q.array.copy(),
                    "e_values": e.array.copy(),
                    "zc_values": zc.array.copy(),
                    "s_values": s.array.copy(),
                    "t_values": zt.array.copy(),
                    "eps1_values": result1["residual"].array.copy(),
                    "eps2_values": result2["residual"].array.copy(),
                    "g2_values": rhs2.array.copy(),
                    "shared_seconds": shared_seconds,
                    "second_feedback_seconds": feedback_seconds,
                    "BAL_H_ledger_seconds": bal_ledger_seconds,
                    "ONE_C_ledger_seconds": one_ledger_seconds,
                    "evaluation_seconds": evaluation_seconds,
                    "forced_balance_audit_seconds": {
                        "BAL_H": bal_audit_seconds,
                        "ONE_C": one_audit_seconds,
                    },
                    "cost": {
                        "start": cost_before,
                        "end": cost_after,
                        "delta": _counter_delta(cost_after, cost_before),
                    },
                    "BAL_H": {
                        "z": _array_summary(z_bal.array[p6_indices]),
                        "z_values": z_bal.array.copy(),
                        "Az_values": az_bal.array.copy(),
                        "field": field_bal,
                        "true_residual_ratio": residual_bal,
                        "true_residual_norm": residual_bal_norm,
                        "total_seconds": shared_seconds + feedback_seconds + bal_ledger_seconds,
                        "inexact_balance": bal_summary,
                        "audit": bal_audit,
                        "I4_first": dict(result1["facts"]),
                        "I4_second": dict(result2["facts"]),
                    },
                    "ONE_C": {
                        "z": _array_summary(z_one.array[p6_indices]),
                        "z_values": z_one.array.copy(),
                        "Az_values": az_one.array.copy(),
                        "field": field_one,
                        "true_residual_ratio": residual_one,
                        "true_residual_norm": residual_one_norm,
                        "total_seconds": shared_seconds + one_ledger_seconds,
                        "inexact_balance": one_summary,
                        "audit": one_audit,
                    },
                    "cell_energies": {
                        "BAL_H": cells_bal,
                        "ONE_C": cells_one,
                        "patch_groups_BAL_H": _seed_energy_groups(cells_bal),
                        "patch_groups_ONE_C": _seed_energy_groups(cells_one),
                    },
                    "input_unchanged": bool(np.array_equal(q.array, q_before)),
                    "shared_I4_calls": 2,
                }
                if not facts["input_unchanged"]:
                    raise ValueError(f"{name} shared control modified q")
                save(f"{name}_shared_zc_s_t", facts)
                summary["shared_framework"].append(facts)
                control_checkpoint(f"shared:{name}")
            finally:
                _destroy(az_one, az_bal, z_one, z_bal, zt, a_s, s, rc, azc, zc,
                         rhs2, rhs1, ae, e, q)
                if result1 is not None:
                    _destroy(result1.get("solution"), result1.get("applied"), result1.get("residual"))
                if result2 is not None:
                    _destroy(result2.get("solution"), result2.get("applied"), result2.get("residual"))

        # A sample is either usable for the complete comparison or excluded
        # as a whole.  Appending each metric independently would silently
        # compare different sample subsets (for example field from sample A
        # and residual from sample B), which is not the frozen M1 rule.
        ratios = {"field": [], "scaled_curl": [], "residual": [], "time": []}
        comparison_ratios: dict[str, Any] = {}
        valid: list[dict[str, Any]] = []
        near_zero: list[str] = []
        for item in summary["shared_framework"]:
            name = item["name"]
            sample_ratios: dict[str, float] = {}
            invalid_reasons: list[str] = []
            for key, bucket in (("L2", "field"), ("scaled_curl", "scaled_curl")):
                ratio, small = _safe_ratio(
                    item["ONE_C"]["field"][key]["relative"],
                    item["BAL_H"]["field"][key]["relative"],
                    common_scale=1.0,
                )
                if ratio is None:
                    invalid_reasons.append(
                        f"{bucket}:{'near_zero' if small else 'missing'}"
                    )
                else:
                    sample_ratios[bucket] = ratio
            ratio, small = _safe_ratio(
                item["ONE_C"]["true_residual_ratio"],
                item["BAL_H"]["true_residual_ratio"],
                common_scale=1.0,
            )
            if ratio is None:
                invalid_reasons.append(
                    f"residual:{'near_zero' if small else 'missing'}"
                )
            else:
                sample_ratios["residual"] = ratio
            ratio, small = _safe_ratio(
                item["ONE_C"]["total_seconds"],
                item["BAL_H"]["total_seconds"],
                common_scale=1.0,
            )
            if ratio is None:
                invalid_reasons.append(f"time:{'near_zero' if small else 'missing'}")
            else:
                sample_ratios["time"] = ratio
            comparison_ratios[name] = {
                "usable_as_one_sample": not invalid_reasons,
                "ratios": sample_ratios,
                "excluded_reasons": invalid_reasons,
            }
            if invalid_reasons:
                near_zero.extend(f"{name}:{reason}" for reason in invalid_reasons)
                continue
            valid.append(item)
            for bucket, ratio in sample_ratios.items():
                ratios[bucket].append(ratio)
        geometric = {key: _geo_mean(value) for key, value in ratios.items()}
        maxima = {key: max(value) if value else None for key, value in ratios.items()}
        bal_time_total = sum(item["BAL_H"]["total_seconds"] for item in valid)
        one_time_total = sum(item["ONE_C"]["total_seconds"] for item in valid)
        cumulative_time_ratio, cumulative_time_near_zero = _safe_ratio(
            one_time_total, bal_time_total, common_scale=1.0,
        )
        if cumulative_time_near_zero:
            near_zero.append("cumulative_time")
        chosen = "BAL_H"
        gate = False
        if len(valid) >= 2:
            gate = bool(
                geometric["field"] is not None and geometric["field"] <= 0.80
                and maxima["field"] is not None and maxima["field"] <= 1.10
                and geometric["scaled_curl"] is not None and geometric["scaled_curl"] <= 1.10
                and geometric["residual"] is not None and geometric["residual"] <= 1.0
                and cumulative_time_ratio is not None and cumulative_time_ratio <= 0.80
            )
            if gate:
                chosen = "ONE_C"
        decision = {
            "selected_framework": chosen,
            "valid_matched_samples": len(valid),
            "matched_samples_total": len(summary["shared_framework"]),
            "authority": "MATCHED_E_Q" if len(valid) >= 2 else "AUTHORITY_LIMITED",
            "gate_pass": gate,
            "ratios_ONE_over_BAL": ratios,
            "comparison_ratios_by_sample": comparison_ratios,
            "geometric_means": geometric,
            "maxima": maxima,
            "time_totals": {
                "BAL_H": bal_time_total,
                "ONE_C": one_time_total,
                "ONE_over_BAL": cumulative_time_ratio,
            },
            "near_zero_denominators": near_zero,
            "thresholds": {
                "field_geometric": 0.80,
                "field_maximum": 1.10,
                "scaled_curl_geometric": 1.10,
                "residual_geometric": 1.0,
                "time_cumulative": 0.80,
            },
            "one_is_not_selected_means_failure": False,
        }
        save("framework_decision", decision)
        control_checkpoint("framework_decision")
        summary["stage_times"]["controls"]["elapsed_seconds"] = (
            time.perf_counter() - controls_start
        )
        summary.update(status="M1_CONTROLS_COMPLETED", framework_decision=decision)
        save("m1_summary", summary)
        return summary
    except BaseException as exc:
        summary["attempted_i4_calls"] = int(i4.calls) if i4 is not None else 0
        summary["completed_i4_calls"] = summary["new_i4_calls"]
        summary["bare_b4_completed_calls"] = summary["bare_b4_calls"]
        if summary["stage_times"]["build"]["elapsed_seconds"] is None:
            summary["stage_times"]["build"]["elapsed_seconds"] = (
                time.perf_counter() - build_start
            )
        if controls_start is not None:
            summary["stage_times"]["controls"]["elapsed_seconds"] = (
                time.perf_counter() - controls_start
            )
        summary.update(status="M1_CONTROLS_FAILED", exception_type=type(exc).__name__,
                       exception=str(exc))
        summary["failure_gate"] = {
            "last_safe_stage": summary.get("last_safe_stage"),
            "stage_times": summary["stage_times"],
            "exception_type": type(exc).__name__,
            "exception": str(exc),
        }
        save("m1_summary", summary)
        raise
    finally:
        if bal_ledger is not None:
            bal_ledger.destroy()
        if one_ledger is not None:
            one_ledger.destroy()
        if metric6 is not None:
            metric6.destroy()
        if metric4 is not None:
            metric4.destroy()
        if stack is not None:
            destroy_macro_stack(stack)


def run_p4_direction_diagnosis(
    cfg: Any,
    comm: Any,
    inventory_path: str | Path,
    directory: str | Path,
    *,
    sample: Callable[[], Any],
    marker: Callable[[str, Any], Any],
    source_sha: str | None = None,
    input_path: str | Path | None = None,
    model_identity: dict[str, Any] | None = None,
    build_started: float | None = None,
    reuse_root: str | Path | None = None,
) -> dict[str, Any]:
    """Run the bounded, reference-free P0--P4 direction diagnosis.

    The runner owns only observation and small dense algebra.  It reuses the
    qualified macro stack and never builds a global p4 matrix or factor.  The
    saved reference fields are used after the calls as measurement/oracle
    diagnostics; neither the I4/B4 path nor the selector receives them.
    """

    from copy import deepcopy

    from src.io.physical_recursive_profile import (
        P4_DIAGNOSIS_LEGACY_WORKSPACE_CAP_BYTES,
        P4_DIAGNOSIS_PRIOR_CHARGED_SECONDS,
        P4_DIAGNOSIS_WORKFLOW_SECONDS,
        P4_DIAGNOSIS_WORKSPACE_CAP_BYTES,
        P4_DIRECTION_DIAGNOSIS_PROFILE,
    )
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.fullspace_physical_intermediate_runtime import level_vector
    from src.solvers.physical_error_metric import LosslessFEMetric
    from src.solvers.physical_macro_dd4 import (
        MacroI4,
        build_macro_stack,
        destroy_macro_stack,
    )
    from src.solvers.physical_p4_direction_diagnosis import (
        RANK_RTOL,
        select_local_response_indices,
        svd_lstsq,
        weighted_mgs_lstsq,
    )
    from .physical_diagnosis_worker import _sha256_file, save_packet
    from .physical_recursive_controls import (
        load_recursive_balanced_inputs,
        load_recursive_calibration,
        verify_recursive_map,
    )
    from .workflow_timebase import CONSERVATIVE_REALTIME, ClockBudget, clock_sample

    if comm.size != 1:
        raise ValueError("p4 direction diagnosis is qualified only for MPI1")
    if reuse_root is None:
        raise ValueError(
            "P4 continuation requires an explicit --p4-direction-reuse-root; "
            "a missing reuse root must not trigger a fresh three-input run"
        )
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)

    def save(name, facts):
        return save_packet(directory, name, facts)

    selected_stems = (
        "A2R160_BAL_H_p4_01",
        "A2R160_BAL_H_p4_02",
        "LIGHT448_BAL_H_p4_09",
    )
    calibration = load_recursive_calibration(inventory_path)
    by_stem = {item["identity"]["stem"]: item for item in calibration}
    if set(by_stem) != {
        "A2R160_BAL_H_p4_01", "A2R160_BAL_H_p4_02",
        "LIGHT448_BAL_H_p4_09", "LIGHT448_BAL_H_p4_10",
        "JOINT448_BAL_H_p4_17", "JOINT448_BAL_H_p4_18",
    }:
        raise ValueError("frozen six-row calibration order or identities changed")
    selected = [by_stem[stem] for stem in selected_stems]
    if not all(item.get("reference_available") for item in selected):
        raise ValueError("P0 requires the three selected reference packets")
    inventory_data = load_recursive_balanced_inputs(inventory_path)
    maps = inventory_data["maps"]
    p6_indices = np.asarray(maps[6]["independent_indices"], dtype=np.int64)
    p4_indices = np.asarray(maps[4]["independent_indices"], dtype=np.int64)
    native_map_sha256 = {
        str(degree): _mapping_identity_sha256(packet)
        for degree, packet in maps.items()
    }

    prior_counts = {
        # These are conservative upper bounds carried from the stopped 01
        # attempt.  They are budget charges, not newly measured continuation
        # actions; the exact old split was not recorded.
        "I4": 1,
        "A4": 49,
        "M0": 13,
        "curl": 49,
        "bare_B4": 1,
        "counted_pc_outputs": 4,
        "M0_pullback": 11,
        "M0_direct_degree4": 2,
        "curl_pullback": 48,
        "curl_direct_degree4": 1,
        "P64_primal": 59,
        "P64_adjoint": 59,
        "P64_primal_attempted_unknown": 1,
    }
    summary: dict[str, Any] = {
        "schema": "task39extra.review-v13.p4-direction-diagnosis.v1",
        "status": "P4_DIRECTION_DIAGNOSIS_STARTED",
        "profile": P4_DIRECTION_DIAGNOSIS_PROFILE,
        "source_sha": source_sha,
        "input_path": str(Path(input_path).resolve()) if input_path is not None else None,
        "inventory_path": str(Path(inventory_path).resolve()),
        "inventory_sha256": _sha256_file(Path(inventory_path)),
        "reuse_root": None if reuse_root is None else str(Path(reuse_root).resolve()),
        "model_identity": dict(model_identity or {}),
        "selected_stems": list(selected_stems),
        "maps": {
            "p6_independent_rows": int(p6_indices.size),
            "p4_independent_rows": int(p4_indices.size),
            "p6_sha256": hashlib.sha256(np.ascontiguousarray(p6_indices).tobytes()).hexdigest(),
            "p4_sha256": hashlib.sha256(np.ascontiguousarray(p4_indices).tobytes()).hexdigest(),
            "native_map_sha256": native_map_sha256,
        },
        "inputs": [],
        "counts": {
            "new_I4": 0,
            "attempted_I4": prior_counts["I4"],
            "completed_I4": prior_counts["I4"],
            "bare_B4": prior_counts["bare_B4"],
            "attempted_B4": prior_counts["bare_B4"],
            "completed_B4": prior_counts["bare_B4"],
            "A4": prior_counts["A4"],
            "M0_pullback": prior_counts["M0_pullback"],
            "curl_pullback": prior_counts["curl_pullback"],
            "M0_direct_degree4": prior_counts["M0_direct_degree4"],
            "curl_direct_degree4": prior_counts["curl_direct_degree4"],
            "P64_primal": prior_counts["P64_primal"],
            "P64_adjoint": prior_counts["P64_adjoint"],
            "P64_primal_attempted": (
                prior_counts["P64_primal"]
                + prior_counts["P64_primal_attempted_unknown"]
            ),
        },
        "prior_counts_upper_bound": prior_counts,
        "limits": {
            "new_I4_max": 3,
            "total_B4_max": 15,
            "A4_max": 200,
            "M0_max": 240,
            "curl_max": 240,
            "build_seconds": 1200.0,
            "per_input_seconds": 1500.0,
            "workflow_seconds": P4_DIAGNOSIS_WORKFLOW_SECONDS,
            "prior_charged_seconds": P4_DIAGNOSIS_PRIOR_CHARGED_SECONDS,
            "remaining_continuation_seconds": (
                P4_DIAGNOSIS_WORKFLOW_SECONDS - P4_DIAGNOSIS_PRIOR_CHARGED_SECONDS
            ),
        },
        "stage_times": {
            "build_seconds": None,
            "diagnosis_seconds": None,
            "total_seconds": None,
        },
        "gates": {},
        "decision": None,
    }

    stack: dict[str, Any] | None = None
    metric4: LosslessFEMetric | None = None
    metric6: LosslessFEMetric | None = None
    i4: MacroI4 | None = None
    build_start = time.perf_counter() if build_started is None else float(build_started)
    continuation_clock = ClockBudget(clock_sample(), policy=CONSERVATIVE_REALTIME)
    controls_start: float | None = None
    input_start: float | None = None
    current_counts: dict[str, int] | None = None
    current_timings: dict[str, float] | None = None
    n4: int | None = None
    reuse_packets: dict[str, Any] | None = None
    ls_workspace_cap_bytes = P4_DIAGNOSIS_WORKSPACE_CAP_BYTES
    if input_path is not None:
        from src.io import load_and_resolve
        resolved_execution = load_and_resolve(input_path).execution
        configured_cap = resolved_execution.get("p4_diagnosis_workspace_cap_bytes")
        if configured_cap != P4_DIAGNOSIS_WORKSPACE_CAP_BYTES:
            raise ValueError(
                "P4 workspace cap must be explicitly configured as 536870912 bytes"
            )
        ls_workspace_cap_bytes = int(configured_cap)
    workspace_peak: dict[str, Any] = {
        "max_estimated_bytes": 0,
        "phase": None,
        "rows": None,
        "columns": None,
        "resident_bytes": 0,
        "non_ls_resident_bytes": 0,
        "metric_storage_bytes": 0,
        "temporary_bytes": 0,
        "cap_bytes": ls_workspace_cap_bytes,
        "legacy_cap_bytes": P4_DIAGNOSIS_LEGACY_WORKSPACE_CAP_BYTES,
    }

    def action_budget_failure(name: str, projected: int, limit: int) -> None:
        save("p4_action_budget_failure", {
            "action": name,
            "projected_count": int(projected),
            "limit": int(limit),
            "summary_counts": dict(summary["counts"]),
            "current_input_counts": dict(current_counts or {}),
        })
        raise RuntimeError(
            f"P4 {name} action budget exceeded: {projected} > {limit}"
        )

    def reserve_action(name: str) -> None:
        if current_counts is None:
            raise RuntimeError(f"{name} action called outside an input")
        checkpoint(f"before_action:{name}")
        limit = None
        if name == "A4":
            limit = 200
        elif name in ("M0_pullback", "M0_direct_degree4"):
            projected = (
                summary["counts"]["M0_pullback"]
                + summary["counts"]["M0_direct_degree4"]
                + current_counts["M0_pullback"]
                + current_counts["M0_direct_degree4"]
                + 1
            )
            if projected > 240:
                action_budget_failure("M0", projected, 240)
        elif name in ("curl_pullback", "curl_direct_degree4"):
            projected = (
                summary["counts"]["curl_pullback"]
                + summary["counts"]["curl_direct_degree4"]
                + current_counts["curl_pullback"]
                + current_counts["curl_direct_degree4"]
                + 1
            )
            if projected > 240:
                action_budget_failure("curl", projected, 240)
        if limit is not None:
            projected = summary["counts"][name] + current_counts[name] + 1
            if projected > limit:
                action_budget_failure(name, projected, limit)
        current_counts[name] += 1

    def _object_array_bytes(value: Any, seen: set[tuple[int, int, int]] | None = None) -> int:
        """Count live ndarray payloads through each array's owning base."""
        if seen is None:
            seen = set()
        if isinstance(value, np.ndarray):
            if value.ndim == 0:
                return 0
            owner = value
            owner_ids: set[int] = set()
            while isinstance(getattr(owner, "base", None), np.ndarray):
                if id(owner) in owner_ids:
                    break
                owner_ids.add(id(owner))
                owner = owner.base
            pointer = int(owner.__array_interface__["data"][0])
            key = (pointer, int(owner.nbytes), int(owner.dtype.itemsize))
            if key in seen:
                return 0
            seen.add(key)
            return int(owner.nbytes)
        if isinstance(value, dict):
            return sum(_object_array_bytes(item, seen) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return sum(_object_array_bytes(item, seen) for item in value)
        return 0

    def _metric_retained_bytes(metric: Any) -> int:
        """Charge retained metric action/bridge buffers outside ndarray walks."""
        if metric is None:
            return 0
        total = 0
        scalar_bytes = np.dtype(np.complex128).itemsize
        for name, action in metric.actions.items():
            audit = getattr(action, "audit", {})
            retained = audit.get("retained_numeric_payload_local_bytes", 0)
            total += int(retained)
            # The last assembled coefficient pack and the kernel's bounded
            # per-apply workspace are not retained by the action's payload
            # audit, but they can coexist with the diagnosis arrays at the
            # instant of a metric call.  Charge both conservatively.
            total += int(audit.get("last_packed_coefficient_bytes", 0) or 0)
            total += int(audit.get("per_apply_bounded_temporary_bytes", 0) or 0)
            bridge = metric.bridges.get(name)
            if bridge is not None:
                total += int(bridge.source.getLocalSize()) * scalar_bytes
                total += int(bridge.target.getLocalSize()) * scalar_bytes
                for attribute in (
                    "indices", "source_slaves", "target_slaves", "target_indices",
                ):
                    total += int(np.asarray(getattr(bridge, attribute)).nbytes)
        if metric is metric6:
            # One pullback_metric_action owns p4 source/output and p6
            # source/target Vecs, plus the independent p6 input/output and
            # the returned p4 array, while the callback is live.  These are
            # transient but are charged here so a dense LS check cannot pass
            # by considering only the retained metric objects.
            total += int(
                2 * int(n4 or 0) * scalar_bytes
                + 2 * int(n6 or 0) * scalar_bytes
                + 2 * int(p6_indices.size) * scalar_bytes
                + int(p4_indices.size) * scalar_bytes
            )
        return int(total)

    def check_live_workspace(
        *,
        label: str,
        resident: tuple[Any, ...] = (),
        background: tuple[Any, ...] = (),
        temporary_bytes: int = 0,
        rows: int | None = None,
        columns: int | None = None,
        weighted: bool | None = None,
    ) -> None:
        """Check a concrete live object set plus a bounded transient reserve."""
        resident_bytes = _object_array_bytes(
            (
                resident, maps, old_packets, selected, summary["inputs"],
                reuse_packets, background,
            )
        )
        metric_storage_bytes = _metric_retained_bytes(metric6)
        resident_bytes += metric_storage_bytes
        temporary_bytes = int(temporary_bytes)
        estimate = resident_bytes + temporary_bytes
        if estimate > int(workspace_peak["max_estimated_bytes"]):
            workspace_peak.update(
                max_estimated_bytes=int(estimate),
                phase=label,
                rows=None if rows is None else int(rows),
                columns=None if columns is None else int(columns),
                resident_bytes=int(resident_bytes),
                non_ls_resident_bytes=int(
                    max(0, resident_bytes - _object_array_bytes(resident))
                ),
                temporary_bytes=int(temporary_bytes),
                metric_storage_bytes=int(metric_storage_bytes),
            )
        if estimate > ls_workspace_cap_bytes:
            save("p4_live_workspace_failure", {
                "label": label,
                "rows": None if rows is None else int(rows),
                "columns": None if columns is None else int(columns),
                "weighted": None if weighted is None else bool(weighted),
                "resident_bytes": int(resident_bytes),
                "non_ls_resident_bytes": int(
                    max(0, resident_bytes - _object_array_bytes(resident))
                ),
                "temporary_bytes": int(temporary_bytes),
                "estimated_bytes": int(estimate),
                "cap_bytes": int(ls_workspace_cap_bytes),
                "summary_counts": dict(summary["counts"]),
                "current_input_counts": dict(current_counts or {}),
            })
            raise MemoryError(
                f"P4 {label} live workspace estimate exceeds "
                f"{ls_workspace_cap_bytes} bytes: {estimate} > "
                f"{ls_workspace_cap_bytes}"
            )

    def check_ls_workspace(
        rows: int,
        columns: int,
        *,
        weighted: bool,
        label: str,
        resident: tuple[Any, ...] = (),
        background: tuple[Any, ...] = (),
    ) -> None:
        """Bound live diagnosis arrays plus the next dense LS workspace.

        The matrix itself is included in ``resident`` by the caller.  The
        estimate is deliberately an upper bound for a scaled copy, economic
        QR factors, the small R-SVD, and the coefficient workspace; this prevents a dense
        solve from passing merely because its temporary buffers were counted
        in isolation from the already-live P1/P2/P3 arrays.
        """
        rank_cap = min(int(rows), int(columns))
        matrix_bytes = int(rows) * int(columns) * np.dtype(np.complex128).itemsize
        if weighted:
            # Include the caller-owned columns, a second contiguous working
            # view, the two MGS basis families, and the current column plus
            # its mass image.  The mass action may also hand back a separate
            # array, so retain one additional row-sized allowance.
            temporary = 2 * matrix_bytes + 2 * int(rows) * rank_cap * 16
            temporary += 3 * int(rows) * 16
            temporary += int(rank_cap) * int(columns) * 16
        else:
            # Count the caller matrix, a scaled Fortran copy, a possible
            # LAPACK work copy, and the economic Q factor.  The small R SVD
            # and Q^H rhs buffers are retained explicitly as well.
            temporary = 3 * matrix_bytes
            temporary += 2 * int(rows) * rank_cap * 16
            temporary += int(rank_cap) * int(columns) * 16
            temporary += int(rank_cap) * int(rank_cap) * 16
            temporary += int(rows) * 16
        check_live_workspace(
            label=label,
            resident=resident,
            background=background,
            temporary_bytes=temporary,
            rows=rows,
            columns=columns,
            weighted=weighted,
        )

    def solve_svd(
        matrix: np.ndarray,
        rhs: np.ndarray,
        *,
        label: str,
        resident: tuple[Any, ...] = (),
        background: tuple[Any, ...] = (),
    ):
        checkpoint(f"before_dense_qr:{label}")
        check_ls_workspace(
            matrix.shape[0], matrix.shape[1], weighted=False,
            label=label, resident=resident + (matrix, rhs), background=background,
        )
        started = time.perf_counter()
        try:
            return svd_lstsq(matrix, rhs, rtol=RANK_RTOL)
        finally:
            if current_timings is not None:
                current_timings["dense_qr_svd_seconds"] += time.perf_counter() - started

    def solve_weighted(
        matrix: np.ndarray,
        rhs: np.ndarray,
        *,
        label: str,
        resident: tuple[Any, ...] = (),
        background: tuple[Any, ...] = (),
    ):
        checkpoint(f"before_weighted_mgs:{label}")
        check_ls_workspace(
            matrix.shape[0], matrix.shape[1], weighted=True,
            label=label, resident=resident + (matrix, rhs), background=background,
        )
        started = time.perf_counter()
        try:
            return weighted_mgs_lstsq(matrix, rhs, mass_apply, rtol=RANK_RTOL)
        finally:
            if current_timings is not None:
                current_timings["weighted_mgs_seconds"] += time.perf_counter() - started

    def update_time_budget(stage: str) -> dict[str, Any]:
        clock_facts = continuation_clock.update(clock_sample())
        formal_elapsed = (
            P4_DIAGNOSIS_PRIOR_CHARGED_SECONDS + clock_facts["budget_seconds"]
        )
        summary["time_budget"] = {
            "policy": CONSERVATIVE_REALTIME,
            "policy_version": clock_facts["policy_version"],
            "stage": stage,
            "prior_charged_seconds": P4_DIAGNOSIS_PRIOR_CHARGED_SECONDS,
            "continuation_seconds": float(clock_facts["budget_seconds"]),
            "formal_accounted_seconds": float(formal_elapsed),
            "remaining_seconds": float(P4_DIAGNOSIS_WORKFLOW_SECONDS - formal_elapsed),
            "clock_facts": clock_facts,
        }
        return clock_facts

    def checkpoint(stage: str) -> Any:
        value = sample()
        update_time_budget(stage)
        formal_elapsed = float(summary["time_budget"]["formal_accounted_seconds"])
        if formal_elapsed > P4_DIAGNOSIS_WORKFLOW_SECONDS:
            raise TimeoutError(
                f"P4 cumulative formal budget exceeded after {stage}: "
                f"{formal_elapsed:.6f}s"
            )
        now = time.perf_counter()
        if controls_start is None:
            elapsed = now - build_start
            summary["stage_times"]["build_seconds"] = elapsed
            if elapsed > 1200.0:
                raise TimeoutError(
                    f"P4 build budget exceeded after {stage}: {elapsed:.6f}s"
                )
        elif input_start is not None:
            elapsed = now - input_start
            if elapsed > 1500.0:
                raise TimeoutError(
                    f"P4 per-input budget exceeded after {stage}: {elapsed:.6f}s"
                )
        return value

    def budget_sample() -> Any:
        return checkpoint("resource_sample")

    def set_full(level: int, values: np.ndarray) -> Any:
        vector = level_vector(stack["levels"], level)
        try:
            _set_full(vector, values, name=f"p{level} full vector")
            result = vector
            vector = None
            return result
        finally:
            _destroy(vector)

    def native_apply(values: np.ndarray) -> np.ndarray:
        if current_counts is None:
            raise RuntimeError("native A4 action called outside an input")
        started = time.perf_counter()
        source = level_vector(stack["levels"], 4)
        output = None
        try:
            _set_full(source, values, name="native A4 input")
            before = np.array(source.array, copy=True)
            reserve_action("A4")
            output = apply_owned(stack["a4_native"], source)
            if not np.array_equal(source.array, before):
                raise ValueError("native A4 modified a diagnosis input")
            result = np.array(output.array, copy=True)
            if not np.isfinite(result).all():
                raise FloatingPointError("native A4 returned non-finite values")
            return result
        finally:
            if output is not None:
                output.destroy()
            source.destroy()
            if current_timings is not None:
                current_timings["native_A4_seconds"] += time.perf_counter() - started

    def coarse_apply(values: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
        """Apply the already-qualified C_U action for repaired P2 fields."""
        started = time.perf_counter()
        source = level_vector(stack["levels"], 4)
        output = None
        try:
            _set_full(source, values, name="C_U input")
            checkpoint("before_C_U_repair")
            output = stack["coarse"].apply(source)
            result = np.array(output.array, copy=True)
            if result.shape != source.array.shape or not np.isfinite(result).all():
                raise ValueError("C_U repair returned an invalid vector")
            bottom_facts = deepcopy(stack["p2_inverse"].last_facts)
            facts = {
                "calls": 1,
                "seconds": float(time.perf_counter() - started),
                "action_identity": stack["coarse"].__class__.__name__ + ":C_U",
                "bottom_facts": bottom_facts,
            }
            return result, facts
        finally:
            _destroy(output, source)

    def coarse_restriction_closure(
        leading_values: np.ndarray,
        residual_values: np.ndarray,
        *,
        label: str,
    ) -> dict[str, Any]:
        """Audit existing C_U balance using its native coarse restriction."""
        started = time.perf_counter()
        leading_source = level_vector(stack["levels"], 4)
        residual_source = level_vector(stack["levels"], 4)
        try:
            _set_full(leading_source, leading_values, name=f"{label} leading")
            _set_full(residual_source, residual_values, name=f"{label} residual")
            checkpoint(f"before_C_U_closure:{label}")
            leading = np.asarray(
                stack["local"].coarse_restriction(leading_source),
                dtype=np.complex128,
            )
            residual = np.asarray(
                stack["local"].coarse_restriction(residual_source),
                dtype=np.complex128,
            )
            leading_norm = float(np.linalg.norm(leading))
            residual_norm = float(np.linalg.norm(residual))
            post_difference = leading - residual
            post_difference_norm = float(np.linalg.norm(post_difference))
            # Match PhysicalBalancedCoupling.balance: the denominator is the
            # original coarse-term norm plus the norm after subtracting the
            # restricted balance residual, not a cancellation-only scale.
            operation_scale = max(
                leading_norm + post_difference_norm, np.finfo(float).tiny
            )
            relative = float(residual_norm / operation_scale)
            facts = {
                "label": label,
                "leading_role": "original_operation_term",
                "residual_role": "C_U_balance_residual",
                "leading_norm": leading_norm,
                "residual_norm": residual_norm,
                "post_difference_norm": post_difference_norm,
                "operation_scale": operation_scale,
                "relative": relative,
                "limit": 1.0e-8,
                "finite": bool(np.isfinite(leading).all() and np.isfinite(residual).all()),
                "restriction_identity": "stack.local.coarse_restriction",
            }
            if not facts["finite"] or not np.isfinite(relative):
                raise ValueError(f"{label} coarse restriction closure is non-finite")
            return facts
        finally:
            _destroy(residual_source, leading_source)
            if current_timings is not None:
                current_timings["coarse_restriction_seconds"] += (
                    time.perf_counter() - started
                )

    def pullback_metric_action(values: np.ndarray, action_name: str) -> np.ndarray:
        """Apply P64^H M06 P64 or P64^H K06 P64 to a p4 full vector."""
        if current_counts is None:
            raise RuntimeError("metric action called outside an input")
        if action_name not in ("mass", "curl"):
            raise ValueError(f"unknown lossless metric action {action_name!r}")
        started = time.perf_counter()
        source4 = level_vector(stack["levels"], 4)
        source6 = target6 = output4 = None
        try:
            _set_full(source4, values, name="p4 metric input")
            source6 = stack["actions"]["transfers"][(6, 4)].apply_primal(source4)
            current_counts["P64_primal"] += 1
            action = metric6.mass if action_name == "mass" else metric6.curl
            if action_name == "mass":
                reserve_action("M0_pullback")
            else:
                reserve_action("curl_pullback")
            independent6 = np.array(source6.array[p6_indices], copy=True)
            metric6_values = np.asarray(action(independent6), dtype=np.complex128)
            if metric6_values.shape != p6_indices.shape or not np.isfinite(metric6_values).all():
                raise ValueError("p6 lossless metric returned an invalid vector")
            target6 = level_vector(stack["levels"], 6)
            _set_independent(target6, metric6_values, p6_indices, name="p6 metric dual")
            output4 = stack["actions"]["transfers"][(6, 4)].apply_adjoint(target6)
            current_counts["P64_adjoint"] += 1
            result = np.array(output4.array[p4_indices], copy=True)
            if not np.isfinite(result).all():
                raise FloatingPointError("pullback metric returned non-finite values")
            return result
        finally:
            _destroy(output4, target6, source6, source4)
            if current_timings is not None:
                key = "pullback_M0_seconds" if action_name == "mass" else "pullback_curl_seconds"
                current_timings[key] += time.perf_counter() - started

    def pullback_metric_square(values: np.ndarray, action_name: str) -> float:
        independent = np.asarray(values, dtype=np.complex128)[p4_indices]
        image = pullback_metric_action(values, action_name)
        value = np.vdot(independent, image)
        scale = max(float(np.linalg.norm(independent) * np.linalg.norm(image)),
                    np.finfo(float).tiny)
        if abs(float(value.imag)) > 1.0e-10 * scale or value.real < -1.0e-10 * scale:
            raise ValueError(f"pullback {action_name} metric is not Hermitian positive")
        return float(max(value.real, 0.0))

    def mass_apply(independent: np.ndarray) -> np.ndarray:
        full = np.zeros(n4, dtype=np.complex128)
        full[p4_indices] = np.asarray(independent, dtype=np.complex128)
        return pullback_metric_action(full, "mass")

    def evaluate_candidate(
        label: str,
        values: np.ndarray,
        applied_independent: np.ndarray,
        rhs: np.ndarray,
        reference: np.ndarray,
        reference_mass_squared: float,
        reference_curl_squared: float,
    ) -> dict[str, Any]:
        error = np.asarray(values, dtype=np.complex128) - reference
        residual = rhs[p4_indices] - np.asarray(applied_independent, dtype=np.complex128)
        rho = float(np.linalg.norm(residual) /
                    max(np.linalg.norm(rhs[p4_indices]), np.finfo(float).tiny))
        mass_squared = pullback_metric_square(error, "mass")
        curl_squared = pullback_metric_square(error, "curl")
        return {
            "label": label,
            "rho": rho,
            "mass_squared": float(mass_squared),
            "curl_squared": float(curl_squared),
            "reference_mass_squared": float(reference_mass_squared),
            "reference_curl_squared": float(reference_curl_squared),
            "mass_error_norm": float(np.sqrt(max(mass_squared, 0.0))),
            "curl_error_norm": float(np.sqrt(max(curl_squared, 0.0))),
            "reference_mass_norm": float(np.sqrt(max(reference_mass_squared, 0.0))),
            "reference_curl_norm": float(np.sqrt(max(reference_curl_squared, 0.0))),
            "eta": float(np.sqrt(mass_squared / reference_mass_squared))
            if reference_mass_squared > 0.0 else None,
            "eta_curl": float(np.sqrt(curl_squared / reference_curl_squared))
            if reference_curl_squared > 0.0 else None,
            "residual_norm": float(np.linalg.norm(residual)),
            "finite": bool(np.isfinite(rho) and np.isfinite(mass_squared)
                            and np.isfinite(curl_squared)),
        }

    def old_control(stem: str) -> tuple[dict[str, Any], Path]:
        candidates = (
            Path("benchmarks/artifacts/task39extra/v12_supplement/7d9df5e19d324776588aaa9efc4996cc3fe36d8e/o1_full_physical_controls/records")
            / f"{stem}_bare_B4_I4.json",
            Path("docs/task039_extra_physical_multilevel/outcomes/records/v12_supplement/core/p4_controls")
            / f"{stem}_bare_B4_I4.json",
        )
        for path in candidates:
            if path.is_file():
                from .physical_diagnostic_completion import load_packet
                packet = load_packet(path)
                if "I4_solution_values" not in packet:
                    raise ValueError(f"old control packet has no I4 solution: {path}")
                return packet, path
        raise FileNotFoundError(f"old four-step control packet is unavailable for {stem}")

    def load_reuse_packets(root_value: str | Path | None) -> dict[str, Any] | None:
        """Load only the hash-bound 01 packets admitted for continuation."""
        if root_value is None:
            return None
        from .physical_diagnostic_completion import load_packet

        root = Path(root_value).resolve()
        records = root / "records"
        if not records.is_dir():
            raise FileNotFoundError(f"P4 reuse root has no records directory: {records}")
        expected_old_source = "e46fec48dc073a745e9b7e6c9186a147aefbc0a0"
        expected_physical = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
        expected_mode = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
        source_path = root / "source_sha.txt"
        model_path = root / "physical_model_sha256.txt"
        if source_path.read_text().strip() != expected_old_source:
            raise ValueError("P4 reuse root is not the qualified e46fec48 continuation source")
        if model_path.read_text().strip() != expected_physical:
            raise ValueError("P4 reuse root physical-model identity differs from the reviewed model")
        launch_path = root / "launch_plan.json"
        if launch_path.is_file():
            launch = json.loads(launch_path.read_text())
            if launch.get("source", {}).get("head") != expected_old_source:
                raise ValueError("P4 reuse launch plan is not bound to the qualified continuation source")
        compact_path = Path(
            "docs/task039_extra_physical_multilevel/outcomes/records/"
            "p4_direction_diagnosis_v13.json"
        )
        if not compact_path.is_file():
            raise FileNotFoundError(f"reviewed P4 compact evidence is missing: {compact_path}")
        compact = json.loads(compact_path.read_text())
        if (
            compact.get("source_sha") != expected_old_source
            or compact.get("physical_model_sha256") != expected_physical
            or compact.get("ordered_mode_sha256") != expected_mode
            or compact.get("p0", {}).get("record_sha256")
            != "c05ff1a34a387e9a2a8a14f492349a4874e3ba160ed254ae11b8533243cfa3e9"
        ):
            raise ValueError("reviewed P4 compact evidence does not bind the qualified source/model/P0")
        expected_npz = {
            "A2R160_BAL_H_p4_01_p1_direction_diagnosis":
                "05df7a25530c22711a76fc7a7fe16f6db9610d691915a52fedfb807a9112c110",
            "A2R160_BAL_H_p4_01_p3_response_columns":
                "c9742f991267015a9bfa811665082772d7e1936237bd0c4339465925dff53759",
        }
        compact_inputs = {
            item["stem"]: item for item in compact.get("inputs", ())
        }
        for name, expected_sha in expected_npz.items():
            entry = compact_inputs.get(selected_stems[0], {}).get(
                "p1" if "p1_" in name else "p3", {}
            )
            if entry.get("npz_sha256") != expected_sha:
                raise ValueError(f"reviewed P4 compact evidence does not bind {name} NPZ")
        old_input_sha_path = root / "input_sha256.txt"
        if old_input_sha_path.is_file() and compact.get("input_sha256") != old_input_sha_path.read_text().strip():
            raise ValueError("P4 reuse root input identity differs from reviewed compact evidence")
        names = (
            "A2R160_BAL_H_p4_01_p1_direction_diagnosis",
            "A2R160_BAL_H_p4_01_p3_response_columns",
            "p0_metric_equivalence",
        )
        packets: dict[str, Any] = {}
        evidence: list[dict[str, Any]] = []
        for name in names:
            json_path = records / f"{name}.json"
            if not json_path.is_file():
                raise FileNotFoundError(f"required P4 reuse packet is missing: {json_path}")
            record = json.loads(json_path.read_text())
            array_meta = record.get("arrays")
            if not isinstance(array_meta, dict):
                raise ValueError(f"P4 reuse packet has no hash-bound array archive: {json_path}")
            array_path = Path(array_meta["path"])
            if not array_path.is_file():
                raise FileNotFoundError(f"P4 reuse array archive is missing: {array_path}")
            json_sha = _sha256_file(json_path)
            array_sha = _sha256_file(array_path)
            if array_sha != array_meta.get("sha256"):
                raise ValueError(f"P4 reuse array hash mismatch: {array_path}")
            expected_array_sha = expected_npz.get(name)
            if expected_array_sha is not None and array_sha != expected_array_sha:
                raise ValueError(
                    f"P4 reuse array is not the frozen reviewed archive for {name}"
                )
            if name == "p0_metric_equivalence":
                expected_p0_json_sha = (
                    "c05ff1a34a387e9a2a8a14f492349a4874e3ba160ed254ae11b8533243cfa3e9"
                )
                if json_sha != expected_p0_json_sha:
                    raise ValueError(
                        "P4 reuse P0 JSON is not the frozen reviewed metric packet"
                    )
            packets[name] = load_packet(json_path)
            evidence.append({
                "name": name,
                "json": str(json_path),
                "json_sha256": json_sha,
                "npz": str(array_path),
                "npz_sha256": array_sha,
            })
        p1 = packets[names[0]]
        p3 = packets[names[1]]
        p0 = packets[names[2]]
        if p1.get("stem") != selected_stems[0] or p3.get("stem") != selected_stems[0]:
            raise ValueError("P4 reuse packets are not for the frozen 01 input")
        frozen_01 = selected[0]
        if not (
            np.array_equal(np.asarray(p1.get("rhs_values")), np.asarray(frozen_01["rhs"]))
            and np.array_equal(np.asarray(p1.get("reference_values")), np.asarray(frozen_01["reference_y"]))
            and np.array_equal(np.asarray(p1.get("reference_A4_values")), np.asarray(frozen_01["reference_A4y"]))
        ):
            raise ValueError("reused P1 g/ref/Aref arrays do not match the frozen 01 calibration")
        if p1.get("operator_identity", {}).get("independent_indices_sha256") != native_map_sha256["4"]:
            raise ValueError("P4 reused P1 native map identity differs from the current map")
        if p3.get("coordinate_map") != "p4_independent" or not np.array_equal(
            np.asarray(p3.get("p4_indices"), dtype=np.int64), p4_indices,
        ):
            raise ValueError("P4 reused P3 coordinate map differs from the current map")
        diagonal = np.asarray(p0.get("fixed_diagonal_values"), dtype=np.float64)
        if diagonal.shape != p4_indices.shape or not np.isfinite(diagonal).all() or np.any(diagonal <= 0.0):
            raise ValueError("P4 reused fixed diagonal is invalid")
        return {
            "root": str(root),
            "records": str(records),
            "packets": packets,
            "evidence": evidence,
            "p1": p1,
            "p3": p3,
            "p0": p0,
            "diagonal": np.array(diagonal, copy=True),
        }

    def interface_blueprint() -> dict[str, Any]:
        carrier = stack["actions"]["physical"][4]["dtn_action"].carrier
        independent = np.asarray(p4_indices, dtype=np.int64)
        legal_set = set(independent.tolist())
        multiplicity: dict[int, int] = {}
        for block in stack["local"].blocks:
            for row in np.asarray(block["indices"], dtype=np.int64):
                row = int(row)
                if row in legal_set:
                    multiplicity[row] = multiplicity.get(row, 0) + 1
        shared_rows = np.asarray(
            sorted(row for row, count in multiplicity.items() if count > 1),
            dtype=np.int64,
        )
        dtn_rows: set[int] = set()
        coupling_nnz = 0
        projection_nnz = 0
        for entry in carrier.entries:
            coupling_rows = np.asarray(entry.coupling_rows, dtype=np.int64)
            coupling_values = np.asarray(entry.coupling_values)
            projection_rows = np.asarray(entry.projection_rows, dtype=np.int64)
            projection_values = np.asarray(entry.projection_values)
            coupling_nnz += int(np.count_nonzero(np.abs(coupling_values) > 0.0))
            projection_nnz += int(np.count_nonzero(np.abs(projection_values) > 0.0))
            dtn_rows.update(
                int(row) for row, value in zip(coupling_rows, coupling_values, strict=True)
                if abs(value) > 0.0 and int(row) in legal_set
            )
            dtn_rows.update(
                int(row) for row, value in zip(projection_rows, projection_values, strict=True)
                if abs(value) > 0.0 and int(row) in legal_set
            )

        gamma0_set = set(shared_rows.tolist()) | dtn_rows
        owner_by_row: dict[int, int] = {}
        for block_index, block in enumerate(stack["local"].blocks):
            for row in np.asarray(block["indices"], dtype=np.int64):
                row = int(row)
                if row in legal_set and row not in gamma0_set:
                    owner_by_row.setdefault(row, int(block_index))

        # ``cell_active`` is the actual macro-cell incidence graph, but its
        # entries are global p4 DOF numbers, not block ordinals.  Resolve
        # those DOFs through the unique interior owner before looking for a
        # cross-I_i cell.  Shared/DtN rows are already interface candidates.
        cross_cells: list[int] = []
        cross_volume_rows: set[int] = set()
        for cell, active in enumerate(stack["local"].cell_active):
            active_owners = {
                owner_by_row[int(row)]
                for row in np.asarray(active, dtype=np.int64)
                if int(row) in owner_by_row
            }
            if len(active_owners) <= 1:
                continue
            cross_cells.append(int(cell))
            cross_volume_rows.update(
                int(row) for row in np.asarray(active, dtype=np.int64)
                if int(row) in owner_by_row
            )

        gamma = np.asarray(
            sorted(set(shared_rows.tolist()) | dtn_rows | cross_volume_rows),
            dtype=np.int64,
        )
        gamma_set = set(gamma.tolist())
        interior = np.asarray(
            sorted(legal_set - gamma_set), dtype=np.int64,
        )
        interface_blocks = [
            int(index) for index, block in enumerate(stack["local"].blocks)
            if np.intersect1d(np.asarray(block["indices"], dtype=np.int64), gamma).size
        ]
        max_local_rows = max(
            int(np.asarray(block["indices"]).size) for block in stack["local"].blocks
        )
        coverage = np.union1d(gamma, interior)
        coverage_defect = np.setdiff1d(independent, coverage)
        structural_status = (
            "STRUCTURAL_INVENTORY_COMPLETE"
            if gamma.size and interface_blocks and coverage_defect.size == 0
            else "STRUCTURAL_INVENTORY_INCOMPLETE"
        )
        return {
            "status": structural_status,
            "blueprint_status": "PENDING_RESPONSE_DOCUMENT",
            "definition": (
                "Gamma is the union of shared macro-block DOF, nonzero current "
                "DtN row/column support, and rows in cells with cross-owner "
                "volume incidence"
            ),
            "I_definition": (
                "I is every legal p4 independent row outside Gamma; this is a "
                "coverage partition, not a guessed block-interior subset"
            ),
            "all_legal_rows": int(independent.size),
            "Gamma_rows": int(gamma.size),
            "I_rows": int(interior.size),
            "shared_macro_dof_rows": int(shared_rows.size),
            "nonzero_DtN_support_rows": int(len(dtn_rows)),
            "cross_volume_cell_count": int(len(cross_cells)),
            "cross_volume_cells": cross_cells,
            "cross_volume_rows": int(len(cross_volume_rows)),
            "covered_rows": int(coverage.size),
            "coverage_defect_rows": int(coverage_defect.size),
            "interface_block_count": int(len(interface_blocks)),
            "interface_block_indices": interface_blocks,
            "macro_block_count": int(len(stack["local"].blocks)),
            "DtN_entry_count": int(len(carrier.entries)),
            "DtN_coupling_nnz": coupling_nnz,
            "DtN_projection_nnz": projection_nnz,
            "Schur_formula": "S_Gamma = A_GammaGamma - A_GammaI A_II^{-1} A_IGamma",
            "operator_identity": (
                "A4 already contains the current cell-volume operator plus the "
                "current DtN action; no separate T_DtN term is added"
            ),
            "coarse_generation_rule": (
                "Defined by the final response blueprint: it must specify the "
                "executable q_Gamma and q_i construction.  This runtime record "
                "provides only the Gamma/I structural inventory and does not "
                "claim an executable coarse-space rule"
            ),
            "restriction_embedding": "R_Gamma^H/R_Gamma and R_i^H/R_i are induced by the native p4 map",
            "capacity_bound": {
                "global_p4_matrix": False,
                "global_factor": False,
                "max_local_block_rows": max_local_rows,
                "local_inventory_cap_bytes": 2684354560,
                "temporary_reserve_bytes": 1073741824,
                "new_dense_schur_bytes_if_materialized": int(gamma.size * gamma.size * 16),
                "implementation": "matrix-free block Schur actions; never materialize the dense Gamma Schur",
            },
        }

    try:
        reuse_packets = load_reuse_packets(reuse_root)
        if reuse_packets is not None:
            summary["reuse_evidence"] = reuse_packets["evidence"]
        # P0 is deliberately completed before any fresh stack construction.
        # This makes missing/changed input, reference, map, or old-return
        # bindings a hard identity failure rather than an expensive PDE
        # failure discovered after the build.
        old_packets: dict[str, tuple[dict[str, Any], Path]] = {}
        p0_rows: list[dict[str, Any]] = []
        for item in selected:
            stem = item["identity"]["stem"]
            old_packet, old_path = old_control(stem)
            rhs_item = np.asarray(item["rhs"], dtype=np.complex128)
            reference_item = np.asarray(item["reference_y"], dtype=np.complex128)
            reference_a4_item = np.asarray(item["reference_A4y"], dtype=np.complex128)
            old_rhs = np.asarray(old_packet["rhs_values"], dtype=np.complex128)
            old_reference = np.asarray(old_packet["reference_values"], dtype=np.complex128)
            old_reference_a4 = np.asarray(
                old_packet["reference_A4y_values"], dtype=np.complex128,
            )
            old_solution = np.asarray(old_packet["I4_solution_values"], dtype=np.complex128)
            if not (
                np.array_equal(old_rhs, rhs_item)
                and np.array_equal(old_reference, reference_item)
                and np.array_equal(old_reference_a4, reference_a4_item)
            ):
                raise ValueError(f"{stem} old control does not bind the frozen P0 arrays")
            identity = item["identity"]
            if hashlib.sha256(np.ascontiguousarray(rhs_item).tobytes()).hexdigest() != identity["g_array_sha256"]:
                raise ValueError(f"{stem} calibration g hash differs from its identity row")
            if old_solution.shape != rhs_item.shape or not np.isfinite(old_solution).all():
                raise ValueError(f"{stem} old I4 solution shape or finiteness gate failed")
            old_reference_residual = np.asarray(
                old_packet["reference_residual_values"], dtype=np.complex128,
            )
            old_reference_ratio = float(
                np.linalg.norm(old_reference_residual)
                / max(np.linalg.norm(old_rhs), np.finfo(float).tiny)
            )
            recorded_reference_ratio = float(old_packet["reference_residual_ratio"])
            if (
                not np.isfinite(old_reference_ratio)
                or not np.isfinite(recorded_reference_ratio)
                or old_reference_ratio > 1.0e-10
                or recorded_reference_ratio > 1.0e-10
                or not np.allclose(
                    old_reference_residual, old_rhs - old_reference_a4,
                    rtol=0.0, atol=1.0e-10,
                )
            ):
                raise ValueError(f"{stem} old reference residual gate failed")
            old_i4 = dict(old_packet.get("I4", {}))
            if (
                int(old_i4.get("max_it", -1)) != 4
                or int(old_i4.get("restart", -1)) != 4
                or not bool(old_i4.get("zero_start", False))
            ):
                raise ValueError(f"{stem} old I4 is not the frozen zero-start FGMRES(4) control")
            # Keep only the old four-step return needed for the later
            # comparison.  The loader has already hash-checked the NPZ; the
            # remaining old packet arrays are not part of the P4 observation.
            old_packets[stem] = ({
                "I4_solution_values": np.array(old_solution, copy=True),
                "reference_residual_ratio": recorded_reference_ratio,
                "I4": old_i4,
            }, old_path)
            p0_rows.append({
                "stem": stem,
                "input_json": identity["input_json"],
                "input_json_sha256": identity["input_sha256"],
                "g_array_sha256": identity["g_array_sha256"],
                "reference_packet": identity["reference_packet"],
                "reference_packet_sha256": identity["reference_packet_sha256"],
                "old_control_packet": str(old_path),
                "old_control_packet_sha256": hashlib.sha256(old_path.read_bytes()).hexdigest(),
                "old_arrays_npz": old_packet.get("arrays"),
                "old_reference_residual_ratio": old_reference_ratio,
                "old_recorded_reference_residual_ratio": recorded_reference_ratio,
                "old_reference_residual_gate": True,
                "old_I4_policy": {
                    "max_it": int(old_i4["max_it"]),
                    "restart": int(old_i4["restart"]),
                    "zero_start": bool(old_i4["zero_start"]),
                },
            })
        save("p0_old_control_preflight", {
            "status": "PASS",
            "selected_rows": p0_rows,
            "reference_ratio_limit": 1.0e-10,
            "zero_reference_ratio_allowed": True,
            "map_sha256": native_map_sha256,
            "source_sha": source_sha,
        })
        selected = [
            {
                "identity": item["identity"],
                "rhs": item["rhs"],
                "reference_y": item["reference_y"],
                "reference_A4y": item["reference_A4y"],
                "reference_available": item["reference_available"],
            }
            for item in selected
        ]
        calibration = None
        by_stem = {}
        inventory_data = None
        marker("p4_direction_inventory_loaded", {
            "selected_stems": list(selected_stems),
            "map_rows": {"p6": int(p6_indices.size), "p4": int(p4_indices.size)},
        })
        stack = build_macro_stack(
            cfg, comm, sample=budget_sample, marker=marker, save=save,
            memory_policy="SYMBOLIC_SIZED_LOCAL_MUMPS_V11",
            local_inventory_cap_bytes=2684354560,
        )
        verify_recursive_map(stack, 6, maps[6])
        verify_recursive_map(stack, 4, maps[4])
        if stack["mode_sha256"] != (
            "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
        ):
            raise ValueError("fresh macro stack mode identity differs from the reviewed P4 mode")
        stack_identity = {
            "profile": P4_DIRECTION_DIAGNOSIS_PROFILE,
            "memory_policy": "SYMBOLIC_SIZED_LOCAL_MUMPS_V11",
            "mode_sha256": stack["mode_sha256"],
            "p4_bridge": stack["a4_bridge"],
            "p2_matrix": stack["p2_matrix_facts"],
            "coverage": stack["local"].coverage,
            "resident_bytes": int(stack["local"].resident_bytes),
            "new_reference_factor": False,
            "p4_global_matrix": False,
            "p4_global_factor": False,
        }
        save("macro_stack_identity", stack_identity)
        summary["macro_stack_identity"] = stack_identity
        interface_structure_inventory = interface_blueprint()
        save("interface_structure_inventory", interface_structure_inventory)
        summary["interface_blueprint"] = interface_structure_inventory
        summary["gates"]["interface_structure"] = (
            interface_structure_inventory["status"] == "STRUCTURAL_INVENTORY_COMPLETE"
        )
        summary["model_identity"].update(
            mode_sha256=stack["mode_sha256"], native_map_sha256=native_map_sha256,
        )
        summary["stage_times"]["build_seconds"] = time.perf_counter() - build_start
        if summary["stage_times"]["build_seconds"] > 1200.0:
            raise TimeoutError("P4 build budget exceeded before diagnosis")
        controls_start = time.perf_counter()

        if reuse_packets is None:
            metric4 = LosslessFEMetric(
                stack["levels"], 4, cfg.k0,
                stack["actions"]["volume_quadrature_metadata"],
            )
        metric6 = LosslessFEMetric(
            stack["levels"], 6, cfg.k0,
            stack["actions"]["volume_quadrature_metadata"],
            build_cell_basis=False,
        )
        probe4 = level_vector(stack["levels"], 4)
        probe6 = level_vector(stack["levels"], 6)
        n4 = int(probe4.array.size)
        n6 = int(probe6.array.size)
        probe4.destroy()
        probe6.destroy()
        p4_position = np.full(n4, -1, dtype=np.int64)
        p4_position[p4_indices] = np.arange(p4_indices.size, dtype=np.int64)
        if n4 != int(maps[4]["independent_indices"].max()) + 1 and n4 <= int(p4_indices.max()):
            raise ValueError("fresh p4 storage vector is incompatible with the native map")
        if n6 <= int(p6_indices.max()):
            raise ValueError("fresh p6 storage vector is incompatible with the native map")
        stack["B4"].capture_vectors = False
        stack["local"].capture_md_observation = False
        stack["local"].last_md_observation = {}
        i4 = MacroI4(
            stack["a4"], stack["a4_native"], stack["B4"],
            sample=budget_sample,
            save=_make_scoped_save(save, ["p4_i4"]),
            stop_requested=lambda: False,
        )

        def run_fresh_i4(stem_value: str, rhs_value: np.ndarray, observed_value: list[dict[str, Any]]):
            rhs_vec = level_vector(stack["levels"], 4)
            result = None
            cost_before = _stack_cost_snapshot(stack, i4)
            try:
                _set_full(rhs_vec, rhs_value, name=f"{stem_value} RHS")
                i4.set_pc_observer(
                    lambda pc_input, pc_output, count: observed_value.append({
                        "count": int(count),
                        "input": np.array(pc_input, copy=True),
                        "output": np.array(pc_output, copy=True),
                    })
                )
                if (
                    summary["counts"]["attempted_I4"] >= 3
                    or summary["counts"]["completed_I4"] >= 3
                ):
                    action_budget_failure(
                        "new_I4", summary["counts"]["attempted_I4"] + 1, 3,
                    )
                summary["counts"]["attempted_I4"] += 1
                result = i4.apply(rhs_vec)
                summary["counts"]["new_I4"] += 1
                summary["counts"]["completed_I4"] += 1
                actual_value = np.array(result["solution"].array, copy=True)
                applied_value = np.array(result["applied"].array, copy=True)
                residual_value = np.array(result["residual"].array, copy=True)
                facts_value = dict(result["facts"])
            except BaseException as exc:
                observed_inputs = (
                    np.column_stack([value["input"] for value in observed_value])
                    if observed_value else np.empty((n4, 0), dtype=np.complex128)
                )
                observed_outputs_partial = (
                    np.column_stack([value["output"] for value in observed_value])
                    if observed_value else np.empty((n4, 0), dtype=np.complex128)
                )
                admission = getattr(i4, "admission", None)
                records = getattr(i4, "records", ())
                failure_packet = {
                    "stem": stem_value,
                    "rhs_values": rhs_value,
                    "observed_pc_inputs_values": observed_inputs,
                    "observed_pc_outputs_values": observed_outputs_partial,
                    "observed_pc_ordinals": np.asarray(
                        [value["count"] for value in observed_value], dtype=np.int64,
                    ),
                    "partial_actual_solution_values": locals().get("actual_value"),
                    "partial_actual_applied_values": locals().get("applied_value"),
                    "partial_actual_residual_values": locals().get("residual_value"),
                    "i4_last_record": dict(records[-1]) if records else {},
                    "i4_admission_last_facts": dict(getattr(admission, "last_facts", {})),
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "operator_identity": {
                        "A4": "fresh native degree-4 volume plus current DtN",
                        "PC": "counted production right-FGMRES preconditioner output",
                        "input_coordinates": "full constrained p4 storage vector",
                        "independent_indices_sha256": native_map_sha256["4"],
                    },
                }
                try:
                    save(f"{stem_value}_p1_observation_failure", failure_packet)
                except BaseException:
                    pass
                raise
            finally:
                i4.set_pc_observer(None)
                if result is not None:
                    _destroy(result.get("solution"), result.get("applied"), result.get("residual"))
                rhs_vec.destroy()
            if actual_value is None or residual_value is None:
                raise RuntimeError(f"{stem_value} I4 returned no solution")
            cost_after = _stack_cost_snapshot(stack, i4)
            return (
                actual_value, applied_value, residual_value, facts_value,
                _counter_delta(cost_after, cost_before),
            )

        def run_fresh_bare(stem_value: str, rhs_value: np.ndarray):
            stack["B4"].capture_vectors = True
            stack["local"].capture_md_observation = True
            stack["local"].last_md_observation = {}
            bare_rhs = level_vector(stack["levels"], 4)
            bare_output = None
            cost_before = _stack_cost_snapshot(stack, i4)
            started = time.perf_counter()
            try:
                if (
                    summary["counts"]["bare_B4"] >= 3
                    or summary["counts"]["attempted_B4"] >= 3
                    or summary["counts"]["completed_B4"] >= 3
                ):
                    action_budget_failure(
                        "bare_B4", summary["counts"]["bare_B4"] + 1, 3,
                    )
                _set_full(bare_rhs, rhs_value, name=f"{stem_value} bare RHS")
                summary["counts"]["attempted_B4"] += 1
                bare_output = stack["B4"].apply(bare_rhs)
                summary["counts"]["bare_B4"] += 1
                summary["counts"]["completed_B4"] += 1
                vectors = dict(stack["B4"].last_apply_vectors)
                observation = dict(stack["local"].last_md_observation)
                facts = dict(stack["B4"].last_apply_facts)
            finally:
                _destroy(bare_output, bare_rhs)
                stack["B4"].capture_vectors = False
                stack["B4"].last_apply_vectors = {}
                stack["local"].capture_md_observation = False
                stack["local"].last_md_observation = {}
            cost_after = _stack_cost_snapshot(stack, i4)
            return (
                vectors, observation, facts,
                float(time.perf_counter() - started),
                _counter_delta(cost_after, cost_before),
            )

        diagonal: np.ndarray | None = None
        metric_gate = True
        all_capture_gate = True
        all_mapping_gate = True
        all_local_gate = True
        all_p1_gate = True
        all_p3_gate = True
        metric_equivalence_records = []

        if reuse_packets is not None:
            # P0 and its fixed diagonal are already qualified and hash-bound.
            # Do not rebuild the direct degree-4 metric or repeat the P0
            # pullbacks during continuation.
            probe_metric_facts = dict(reuse_packets["p0"]["facts"])
            diagonal = np.array(reuse_packets["diagonal"], copy=True)
            metric_gate = bool(
                all(
                    np.isfinite(float(facts.get(key, np.inf)))
                    and float(facts.get(key, np.inf)) <= 1.0e-10
                    for facts in probe_metric_facts.get("actions", {}).values()
                    for key in ("output_relative", "square_relative")
                )
            )
            metric_equivalence_records.append({
                "reuse": True,
                "source": reuse_packets["evidence"][-1],
                "facts": probe_metric_facts,
            })
            save("p0_metric_equivalence_reused", {
                "source": reuse_packets["evidence"][-1],
                "facts": probe_metric_facts,
                "fixed_diagonal": _array_summary(diagonal),
                "counts": dict(reuse_packets["p0"].get("counts", {})),
            })
        else:
            # Degree-4 direct and P6 pullback metrics are compared on a fresh
            # deterministic vector before any reference field is touched.
            current_counts = {
                "A4": 0, "M0_pullback": 0, "curl_pullback": 0,
                "M0_direct_degree4": 0, "curl_direct_degree4": 0,
                "P64_primal": 0, "P64_adjoint": 0,
            }
            probe_raw = (
                np.arange(p4_indices.size, dtype=np.float64) + 1.0
                + 1j * (1.0 + np.arange(p4_indices.size, dtype=np.float64) % 17.0)
            ).astype(np.complex128)
            probe_max_abs = float(np.max(np.abs(probe_raw)))
            probe_l2 = float(np.linalg.norm(probe_raw))
            probe_scale = max(probe_max_abs, probe_l2, np.finfo(float).tiny)
            probe_independent = np.ascontiguousarray(probe_raw / probe_scale)
            probe_full = np.zeros(n4, dtype=np.complex128)
            probe_full[p4_indices] = probe_independent
            direct_metrics: dict[str, np.ndarray] = {}
            pullback_metrics: dict[str, np.ndarray] = {}
            for name, direct_action in (("mass", metric4.mass), ("curl", metric4.curl)):
                direct_counter = {
                    "mass": "M0_direct_degree4",
                    "curl": "curl_direct_degree4",
                }[name]
                reserve_action(direct_counter)
                direct_metrics[name] = np.ascontiguousarray(
                    direct_action(probe_independent), dtype=np.complex128,
                )
                pullback_metrics[name] = pullback_metric_action(probe_full, name)
            probe_metric_facts = {
                "vector_role": "deterministic_reference_free_probe",
                "normalization": {
                    "raw_vector_summary": _array_summary(probe_raw),
                    "raw_max_abs": probe_max_abs,
                    "raw_l2_norm": probe_l2,
                    "scale": probe_scale,
                    "normalized_max_abs": float(np.max(np.abs(probe_independent))),
                    "normalized_l2_norm": float(np.linalg.norm(probe_independent)),
                    "rule": "divide by max(max_abs, l2_norm) so both max and 2-norm are bounded",
                },
                "vector_summary": _array_summary(probe_independent),
                "quadrature": stack["actions"]["volume_quadrature_metadata"],
                "constraint_map_sha256": native_map_sha256["4"],
                "constraint_map_identity": stack["local"].mapping_identity_sha256,
                "actions": {},
            }
            for name in ("mass", "curl"):
                direct = direct_metrics[name]
                pullback = pullback_metrics[name]
                relative = _relative(direct, pullback)
                direct_square = float(np.real(np.vdot(probe_independent, direct)))
                pullback_square = float(np.real(np.vdot(probe_independent, pullback)))
                probe_metric_facts["actions"][name] = {
                    "direct_output_summary": _array_summary(direct),
                    "pullback_output_summary": _array_summary(pullback),
                    "output_relative": relative,
                    "direct_square": direct_square,
                    "pullback_square": pullback_square,
                    "square_relative": float(
                        abs(direct_square - pullback_square)
                        / max(abs(pullback_square), np.finfo(float).tiny)
                    ),
                    "limit": 1.0e-10,
                }
                if (
                    not np.isfinite(relative)
                    or relative > 1.0e-10
                    or probe_metric_facts["actions"][name]["square_relative"] > 1.0e-10
                ):
                    metric_gate = False
            metric_equivalence_records.append(probe_metric_facts)
            if metric_gate:
                diagonal = np.asarray(metric4.diagonal(checkpoint=budget_sample), dtype=np.float64)
                if (
                    diagonal.shape != p4_indices.shape
                    or not np.isfinite(diagonal).all()
                    or np.any(diagonal <= 0.0)
                ):
                    metric_gate = False
                    diagonal = None
            save("p0_metric_equivalence", {
                "facts": probe_metric_facts,
                "fixed_diagonal": None if diagonal is None else _array_summary(diagonal),
                "fixed_diagonal_values": diagonal,
                "counts": dict(current_counts),
            })
            for key in current_counts:
                summary["counts"][key] += current_counts[key]
            current_counts = None
            metric4.destroy()
            metric4 = None
            del direct_metrics, pullback_metrics, probe_raw, probe_independent, probe_full
            gc.collect()

        for ordinal, item in enumerate(selected, start=1):
            stem = item["identity"]["stem"]
            reuse_input = reuse_packets is not None and stem == selected_stems[0]
            input_start = time.perf_counter()
            current_counts = {
                "A4": 0, "M0_pullback": 0, "curl_pullback": 0,
                "M0_direct_degree4": 0, "curl_direct_degree4": 0,
                "P64_primal": 0, "P64_adjoint": 0,
            }
            current_timings = {
                "native_A4_seconds": 0.0,
                "pullback_M0_seconds": 0.0,
                "pullback_curl_seconds": 0.0,
                "dense_qr_svd_seconds": 0.0,
                "weighted_mgs_seconds": 0.0,
                "selector_seconds": 0.0,
                "p3_42_Ap_i_seconds": 0.0,
                "p3_A_t_seconds": 0.0,
                "p2_42_p_i_curl_seconds": 0.0,
                "coarse_restriction_seconds": 0.0,
            }
            if reuse_input:
                # The qualified 01 packet carries complete vectors and
                # identities, but it did not record these continuation-stage
                # wall times.  Keep them explicitly unknown instead of
                # turning reused work into synthetic zero-cost evidence.
                current_timings.update({
                    "selector_seconds": None,
                    "p3_42_Ap_i_seconds": None,
                    "p3_A_t_seconds": None,
                })
            rhs = np.asarray(item["rhs"], dtype=np.complex128)
            reference = np.asarray(item["reference_y"], dtype=np.complex128)
            expected_reference_a4 = np.asarray(item["reference_A4y"], dtype=np.complex128)
            if rhs.shape != (n4,) or reference.shape != (n4,) or expected_reference_a4.shape != (n4,):
                raise ValueError(f"{stem} p4 vector shapes do not match the fresh stack")
            if not np.isfinite(rhs).all() or not np.isfinite(reference).all():
                raise ValueError(f"{stem} p4 calibration values are not finite")
            old_packet, old_path = old_packets[stem]
            old_solution = np.asarray(old_packet["I4_solution_values"], dtype=np.complex128)
            if old_solution.shape != (n4,) or not np.isfinite(old_solution).all():
                raise ValueError(f"{stem} old I4 solution shape or finiteness gate failed")
            reuse_p1 = None if not reuse_input else reuse_packets["p1"]
            reuse_p3 = None if not reuse_input else reuse_packets["p3"]
            reference_slaves = np.asarray(maps[4]["slaves"], dtype=np.int64)
            if np.any(reference[reference_slaves] != 0.0):
                raise ValueError(f"{stem} reference field is not slave-zero")

            if reuse_input:
                reuse_rhs = np.asarray(reuse_p1["rhs_values"], dtype=np.complex128)
                reuse_reference = np.asarray(reuse_p1["reference_values"], dtype=np.complex128)
                if not (np.array_equal(reuse_rhs, rhs) and np.array_equal(reuse_reference, reference)):
                    raise ValueError("reused P1 packet does not bind the frozen 01 input")
                reference_a4 = np.array(
                    reuse_p1["reference_A4_values"], dtype=np.complex128, copy=True,
                )
            else:
                reference_a4 = native_apply(reference)
            reference_bridge = _relative(reference_a4, expected_reference_a4)
            r_ref = rhs - reference_a4
            r_ref_ratio = float(np.linalg.norm(r_ref) /
                                max(np.linalg.norm(rhs), np.finfo(float).tiny))
            if not np.isfinite(reference_bridge) or reference_bridge > 1.0e-10:
                all_mapping_gate = False
            r_ref_gate = bool(np.isfinite(r_ref_ratio) and r_ref_ratio <= 1.0e-10)
            if not r_ref_gate:
                all_mapping_gate = False

            if reuse_input:
                reuse_p1_facts = reuse_p1["facts"]
                reference_mass_squared = float(reuse_p1_facts["reference_mass_squared"])
                reference_curl_squared = float(reuse_p1_facts["reference_curl_squared"])
            else:
                reference_mass_squared = pullback_metric_square(reference, "mass")
                reference_curl_squared = pullback_metric_square(reference, "curl")
            if reference_mass_squared <= 0.0 or reference_curl_squared <= 0.0:
                metric_gate = False

            metric_equivalence = float(
                max(
                    probe_metric_facts["actions"]["mass"]["output_relative"],
                    probe_metric_facts["actions"]["mass"]["square_relative"],
                    probe_metric_facts["actions"]["curl"]["output_relative"],
                    probe_metric_facts["actions"]["curl"]["square_relative"],
                )
            )

            observed: list[dict[str, Any]] = []

            def observe(pc_input: np.ndarray, pc_output: np.ndarray, count: int) -> None:
                observed.append({
                    "count": int(count),
                    "input": np.array(pc_input, copy=True),
                    "output": np.array(pc_output, copy=True),
                })

            if reuse_input:
                actual = np.array(
                    reuse_p1["actual_solution_values"], dtype=np.complex128, copy=True,
                )
                actual_applied = np.array(
                    reuse_p1["actual_applied_values"], dtype=np.complex128, copy=True,
                )
                # The full residual vector is reconstructed from the frozen
                # P1 identity, not from a new A4 call.
                actual_residual = rhs - actual_applied
                Z = np.array(
                    reuse_p1["pc_outputs_values"], dtype=np.complex128, copy=True,
                )
                Q = np.array(
                    reuse_p1["A_pc_outputs_values"], dtype=np.complex128, copy=True,
                )
                observed_outputs = [
                    np.asarray(Z[:, index], dtype=np.complex128)
                    for index in range(Z.shape[1])
                ]
                observed_count = int(Z.shape[1])
                observed_ordinals = [int(value) for value in np.asarray(
                    reuse_p1["observed_pc_ordinals"], dtype=np.int64,
                )]
                i4_facts = dict(reuse_p1["facts"].get("I4", {}))
                i4_facts.update({
                    "reuse": True,
                    "old_packet_reused": True,
                    "timing_status": "not_recorded_in_qualified_01_packet",
                    "timing_source": "frozen_01_p1_packet",
                })
                i4_cost_delta = {
                    "reuse": True,
                    "timing_status": "unknown",
                    "timing_source": "frozen_01_p1_packet",
                }
                capture_gate = bool(
                    1 <= observed_count <= 4
                    and observed_count == len(observed_ordinals)
                    and Z.shape == (n4, observed_count)
                    and Q.shape == (n4, observed_count)
                    and np.isfinite(Z).all() and np.isfinite(Q).all()
                )
                actual_identity = float(reuse_p1["facts"]["actual_applied_plus_residual_relative"])
                actual_native_identity = float(reuse_p1["facts"]["actual_native_A4_vs_applied_relative"])
                actual_i4_consistency_gate = bool(
                    reuse_p1["facts"].get("actual_i4_consistency_gate", False)
                )
                actual_native = np.array(actual_applied, copy=True)
            else:
                observed = []
                actual, actual_applied, actual_residual, i4_facts, i4_cost_delta = (
                    run_fresh_i4(stem, rhs, observed)
                )
                observed_outputs = [item["output"] for item in observed]
                observed_count = len(observed_outputs)
                b4_in_facts = int(i4_facts.get("B4_calls", observed_count))
                capture_gate = bool(
                    1 <= observed_count <= 4
                    and observed_count == b4_in_facts
                    and all(np.asarray(value).shape == (n4,) for value in observed_outputs)
                    and all(np.isfinite(value).all() for value in observed_outputs)
                )
                actual_native = native_apply(actual)
                actual_identity = _operation_relative(
                    actual_applied + actual_residual,
                    rhs,
                    actual_applied, actual_residual, rhs,
                )
                actual_native_identity = _operation_relative(
                    actual_native, actual_applied, actual_native, actual_applied,
                )
                actual_i4_consistency_gate = bool(
                    np.isfinite(actual_identity)
                    and actual_identity <= 1.0e-10
                    and np.isfinite(actual_native_identity)
                    and actual_native_identity <= 1.0e-10
                )
            all_capture_gate = all_capture_gate and capture_gate
            if not capture_gate:
                raise RuntimeError(f"{stem} counted-PC capture gate failed")
            if actual_applied is None:
                raise RuntimeError(f"{stem} I4 returned no applied vector")
            rhs_ind = rhs[p4_indices]
            reference_ind = reference[p4_indices]
            if not reuse_input:
                actual_native = native_apply(actual)
                actual_identity = _operation_relative(
                    actual_applied + actual_residual,
                    rhs,
                    actual_applied, actual_residual, rhs,
                )
                actual_native_identity = _operation_relative(
                    actual_native, actual_applied, actual_native, actual_applied,
                )
                actual_i4_consistency_gate = bool(
                    np.isfinite(actual_identity)
                    and actual_identity <= 1.0e-10
                    and np.isfinite(actual_native_identity)
                    and actual_native_identity <= 1.0e-10
                )
                all_p1_gate = all_p1_gate and actual_i4_consistency_gate
                Z = np.ascontiguousarray(np.column_stack(observed_outputs), dtype=np.complex128)
                Q = np.ascontiguousarray(
                    np.column_stack([native_apply(column) for column in Z.T]),
                    dtype=np.complex128,
                )
                Z_ind = Z[p4_indices, :]
                Q_ind = Q[p4_indices, :]
                reconstruction_y, reconstruction_facts = solve_svd(
                    Z_ind, actual[p4_indices],
                    label=f"{stem}:P1_actual_reconstruction",
                    resident=(Z, Q, actual, actual_native),
                )
                reconstructed_actual_ind = Z_ind @ reconstruction_y
                reconstruction_scale = max(
                    float(np.linalg.norm(actual[p4_indices])),
                    float(np.linalg.norm(Z_ind) * np.linalg.norm(reconstruction_y)),
                    np.finfo(float).tiny,
                )
                reconstruction_relative = float(
                    np.linalg.norm(actual[p4_indices] - reconstructed_actual_ind)
                    / reconstruction_scale
                )
                residual_y, residual_facts = solve_svd(
                    Q_ind, rhs_ind, label=f"{stem}:P1_residual",
                    resident=(Z, Q, actual, actual_native),
                )
                residual_values = Z @ residual_y
                field_y = dual_y = None
                field_values = dual_values = None
                field_facts = dual_facts = None
                if metric_gate:
                    field_y, field_facts = solve_weighted(
                        Z_ind, reference_ind, label=f"{stem}:P1_field",
                        resident=(Z, Q, actual, actual_native),
                    )
                    field_values = Z @ field_y
                    if diagonal is not None:
                        sqrt_diagonal = np.sqrt(diagonal)
                        dual_y, dual_facts = solve_svd(
                            Q_ind / sqrt_diagonal[:, None],
                            rhs_ind / sqrt_diagonal,
                            label=f"{stem}:P1_dual_mass",
                            resident=(Z, Q, actual, actual_native),
                        )
                        dual_values = Z @ dual_y
                actual_rho = float(np.linalg.norm(actual_residual[p4_indices]) /
                                   max(np.linalg.norm(rhs_ind), np.finfo(float).tiny))
                residual_projection = Q_ind @ residual_y
                actual_rhs_residual = rhs_ind - actual_applied[p4_indices]
                reconstructed_rhs_residual = rhs_ind - residual_projection
                min_rho_numerator = abs(
                    float(np.linalg.norm(reconstructed_rhs_residual))
                    - float(np.linalg.norm(actual_rhs_residual))
                )
                min_rho_scale = max(
                    float(np.linalg.norm(rhs_ind)),
                    float(np.linalg.norm(Q_ind) * np.linalg.norm(residual_y)),
                    float(np.linalg.norm(actual_applied[p4_indices])),
                    np.finfo(float).tiny,
                )
                reconstruction_gate = bool(
                    np.isfinite(reconstruction_relative)
                    and reconstruction_relative <= 1.0e-10
                )
                min_rho_gate = bool(
                    np.isfinite(min_rho_numerator)
                    and np.isfinite(min_rho_scale)
                    and min_rho_numerator / min_rho_scale <= 1.0e-10
                )
                all_p1_gate = all_p1_gate and reconstruction_gate and min_rho_gate
                candidate_facts = {
                    "actual": evaluate_candidate(
                        "actual", actual, actual_applied[p4_indices],
                        rhs, reference, reference_mass_squared, reference_curl_squared,
                    ),
                    "Z_residual": evaluate_candidate(
                        "Z_residual", residual_values, (Q @ residual_y)[p4_indices],
                        rhs, reference, reference_mass_squared, reference_curl_squared,
                    ),
                }
                candidate_facts["actual"]["rho"] = actual_rho
                if field_values is not None:
                    candidate_facts["Z_field"] = evaluate_candidate(
                        "Z_field", field_values, (Q @ field_y)[p4_indices],
                        rhs, reference, reference_mass_squared, reference_curl_squared,
                    )
                if dual_values is not None:
                    candidate_facts["Z_dual_mass"] = evaluate_candidate(
                        "Z_dual_mass", dual_values, (Q @ dual_y)[p4_indices],
                        rhs, reference, reference_mass_squared, reference_curl_squared,
                    )
                p1_facts = {
                    "residual_LS": residual_facts,
                    "actual_reconstruction_LS": reconstruction_facts,
                    "field_LS": field_facts,
                    "dual_mass_LS": dual_facts,
                    "actual_reconstruction_relative": reconstruction_relative,
                    "actual_reconstruction_scale": reconstruction_scale,
                    "actual_reconstruction_gate": reconstruction_gate,
                    "min_rho_numerator": min_rho_numerator,
                    "min_rho_scale": min_rho_scale,
                    "min_rho_gate": min_rho_gate,
                    "actual_i4_consistency_gate": actual_i4_consistency_gate,
                    "actual_applied_plus_residual_relative": actual_identity,
                    "actual_native_A4_vs_applied_relative": actual_native_identity,
                    "reference_mass_squared": reference_mass_squared,
                    "reference_curl_squared": reference_curl_squared,
                    "metric_equivalence": metric_equivalence,
                    "candidates": {key: value for key, value in candidate_facts.items()},
                }
            else:
                Z_ind = Z[p4_indices, :]
                Q_ind = Q[p4_indices, :]
                reconstruction_y = np.asarray(reuse_p1["reconstruction_y"], dtype=np.complex128)
                residual_y = np.asarray(reuse_p1["residual_y"], dtype=np.complex128)
                field_y = None if reuse_p1.get("field_y") is None else np.asarray(reuse_p1["field_y"], dtype=np.complex128)
                dual_y = None if reuse_p1.get("dual_y") is None else np.asarray(reuse_p1["dual_y"], dtype=np.complex128)
                reconstruction_facts = reuse_p1["facts"].get("actual_reconstruction_LS")
                residual_facts = reuse_p1["facts"].get("residual_LS")
                field_facts = reuse_p1["facts"].get("field_LS")
                dual_facts = reuse_p1["facts"].get("dual_mass_LS")
                reconstruction_relative = float(reuse_p1["facts"]["actual_reconstruction_relative"])
                reconstruction_scale = float(reuse_p1["facts"]["actual_reconstruction_scale"])
                reconstruction_gate = bool(reuse_p1["facts"]["actual_reconstruction_gate"])
                min_rho_numerator = float(reuse_p1["facts"]["min_rho_numerator"])
                min_rho_scale = float(reuse_p1["facts"]["min_rho_scale"])
                min_rho_gate = bool(reuse_p1["facts"]["min_rho_gate"])
                residual_values = Z @ residual_y
                field_values = None if field_y is None else Z @ field_y
                dual_values = None if dual_y is None else Z @ dual_y
                actual_rho = float(reuse_p1["facts"]["candidates"]["actual"]["rho"])
                candidate_facts = {
                    key: dict(value) for key, value in reuse_p1["facts"]["candidates"].items()
                }
                p1_facts = dict(reuse_p1["facts"])
                all_p1_gate = all_p1_gate and actual_i4_consistency_gate and reconstruction_gate and min_rho_gate
            if reuse_input:
                all_p1_gate = all_p1_gate and capture_gate
            p1_facts["continuation_action_counts"] = (
                {"status": "reused", "new_A4": 0, "new_metric_actions": 0}
                if reuse_input else dict(current_counts)
            )
            p1_facts["continuation_timings"] = (
                {
                    "status": "unknown_in_qualified_01_packet",
                    "i4_seconds": None,
                    "source": "frozen_01_p1_packet",
                }
                if reuse_input else dict(current_timings)
            )
            p1_facts["i4_facts"] = deepcopy(i4_facts)
            p1_facts["i4_cost_delta"] = deepcopy(i4_cost_delta)
            p1_facts["observed_count"] = int(observed_count)
            p1_facts["summary_counts_snapshot"] = dict(summary["counts"])
            p1_facts["current_input_counts_snapshot"] = dict(current_counts)
            save(f"{stem}_p1_direction_diagnosis", {
                "stem": stem,
                "rhs_values": rhs,
                "reference_values": reference,
                "reference_A4_values": reference_a4,
                "r_ref_values": r_ref,
                "old_solution_values": old_solution,
                "actual_solution_values": actual,
                "actual_applied_values": actual_applied,
                "pc_outputs_values": Z,
                "A_pc_outputs_values": Q,
                "reconstruction_y": reconstruction_y,
                "residual_y": residual_y,
                "field_y": field_y,
                "dual_y": dual_y,
                "observed_pc_inputs_values": (
                    np.asarray(reuse_p1["observed_pc_inputs_values"], dtype=np.complex128)
                    if reuse_input else np.column_stack(
                        [value["input"] for value in observed]
                    )
                ),
                "observed_pc_ordinals": (
                    np.asarray(reuse_p1["observed_pc_ordinals"], dtype=np.int64)
                    if reuse_input else np.asarray(
                        [value["count"] for value in observed], dtype=np.int64,
                    )
                ),
                "operator_identity": {
                    "A4": "fresh native degree-4 volume plus current DtN",
                    "Q": "native A4 applied to counted production PC outputs",
                    "input_coordinates": "full constrained p4 storage vector",
                    "independent_indices_sha256": native_map_sha256["4"],
                },
                "facts": p1_facts,
            })
            if not reuse_input:
                observed_ordinals = [int(value["count"]) for value in observed]
            # P1 is now hash-bound on disk.  Keep only independent Z/Q views
            # for the later L construction; the full observed packet and
            # duplicate full output columns are no longer live.
            observed.clear()
            del observed_outputs, actual_native, actual_applied, Z, Q
            actual_residual = None
            residual_values = None
            field_values = None
            dual_values = None
            reconstruction_y = None
            residual_y = None
            field_y = None
            dual_y = None
            if reuse_input:
                reuse_packets["packets"].pop(
                    "A2R160_BAL_H_p4_01_p1_direction_diagnosis", None,
                )
                reuse_packets["p1"] = None
                reuse_p1 = None
            gc.collect()

            p_columns_source = None
            p_images_source = None
            A_a_source = None
            A_t_source = None
            b4_vectors = None
            md_observation = {}
            blocks = []
            source_block = None
            if reuse_input:
                # Borrow the hash-bound P3 arrays until the single continuation
                # arena is filled.  Copies here would make old P3, copied P3,
                # and L/AL coexist unnecessarily.
                p_columns_source = np.asarray(
                    reuse_p3["p_columns_values"], dtype=np.complex128,
                )
                p_images_source = np.asarray(
                    reuse_p3["p_images_values"], dtype=np.complex128,
                )
                A_a_source = np.asarray(reuse_p3["A_a_values"], dtype=np.complex128)
                A_t_source = np.asarray(reuse_p3["A_t_values"], dtype=np.complex128)
                p_columns_ind = p_columns_source
                if p_columns_source.shape != (p4_indices.size, 42) or p_images_source.shape != p_columns_source.shape:
                    raise ValueError("reused P3 response columns have incompatible shapes")
                a, c_u_g_facts = coarse_apply(rhs)
                A_a_ind = A_a_source
                A_t_ind = A_t_source
                A_a = _full_from_independent(n4, p4_indices, A_a_ind)
                ad = _full_from_independent(n4, p4_indices, np.sum(p_images_source, axis=1))
                d = _full_from_independent(n4, p4_indices, np.sum(p_columns_source, axis=1))
                t, c_u_ad_facts = coarse_apply(ad)
                h = rhs - A_a
                bare_seconds = None
                bare_apply_facts = {
                    "reuse": True,
                    "timing_status": "not_recorded_in_qualified_01_packet",
                    "counts": {"C": 2},
                    "operation_seconds": {"C": (
                        c_u_g_facts["seconds"] + c_u_ad_facts["seconds"]
                    )},
                    "initial": {"constraint": "repaired_from_C_U(g)"},
                    "feedback": {"constraint": "repaired_from_C_U(A_d)"},
                    "bottom_facts": {
                        "initial": deepcopy(c_u_g_facts.get("bottom_facts", {})),
                        "feedback": deepcopy(c_u_ad_facts.get("bottom_facts", {})),
                    },
                }
                bare_cost_delta = {"reuse": True, "timing_status": "unknown"}
                for block_index, source_block in enumerate(stack["local"].blocks):
                    indices = np.asarray(source_block["indices"], dtype=np.int64)
                    weights = np.asarray(stack["local"].output_weights[indices], dtype=np.float64)
                    positions = p4_position[indices]
                    weighted = np.zeros(indices.size, dtype=np.complex128)
                    valid = positions >= 0
                    weighted[valid] = p_columns_ind[positions[valid], block_index]
                    if np.any(weights[valid] <= 0.0) or not np.isfinite(weights).all():
                        raise ValueError(f"{stem} cannot recover local PoU weights for reused P3")
                    di = np.zeros(indices.size, dtype=np.complex128)
                    positive = weights > 0.0
                    di[positive] = weighted[positive] / weights[positive]
                    if not np.isfinite(di).all():
                        raise ValueError(f"{stem} recovered local d_i is non-finite")
                    blocks.append({
                        "block_index": int(block_index),
                        "indices": indices.copy(),
                        "d_i": di,
                        "weighted_values": weighted,
                        "weights": weights,
                    })
                capture_md_gate = bool(len(blocks) == 42)
            else:
                b4_vectors, md_observation, bare_apply_facts, bare_seconds, bare_cost_delta = (
                    run_fresh_bare(stem, rhs)
                )
                bare_apply_facts["bottom_facts"] = {
                    "last_C_U": deepcopy(stack["p2_inverse"].last_facts),
                    "status": "last_C_U_of_single_bare_B4_is_captured",
                }
                required_vectors = ("zc", "rc", "s", "A6s", "c2")
                if any(b4_vectors.get(name) is None for name in required_vectors):
                    raise RuntimeError(f"{stem} B4 vector capture is incomplete")
                a = np.asarray(b4_vectors["zc"], dtype=np.complex128)
                h = np.asarray(b4_vectors["rc"], dtype=np.complex128)
                d = np.asarray(b4_vectors["s"], dtype=np.complex128)
                ad = np.asarray(b4_vectors["A6s"], dtype=np.complex128)
                t = np.asarray(b4_vectors["c2"], dtype=np.complex128)
                blocks = sorted(
                    md_observation.get("blocks", ()),
                    key=lambda value: value["block_index"],
                )
                capture_md_gate = bool(
                    len(blocks) == 42
                    and [int(block["block_index"]) for block in blocks] == list(range(42))
                )
            all_capture_gate = all_capture_gate and capture_md_gate
            if not capture_md_gate:
                raise RuntimeError(f"{stem} local response capture gate failed")
            e_h = reference - a
            A_a = rhs - h
            A_eh = reference_a4 - A_a
            eh_identity = _operation_relative(
                A_eh, h - r_ref, A_eh, h, r_ref,
            )
            if not np.isfinite(eh_identity) or eh_identity > 1.0e-10:
                all_local_gate = False
            pou = np.zeros(n4, dtype=np.float64)
            recomposed = np.zeros(n4, dtype=np.complex128)
            local_records = []
            if not reuse_input:
                p_columns_ind = np.zeros(
                    (p4_indices.size, len(blocks)), dtype=np.complex128,
                )
            for local_column, block in enumerate(blocks):
                block_index = int(block["block_index"])
                indices = np.asarray(block["indices"], dtype=np.int64)
                di = np.asarray(block["d_i"], dtype=np.complex128)
                weighted = np.asarray(block["weighted_values"], dtype=np.complex128)
                weights = np.asarray(block["weights"], dtype=np.float64)
                np.add.at(pou, indices, weights)
                positions = p4_position[indices]
                valid = positions >= 0
                p_columns_ind[positions[valid], local_column] = weighted[valid]
                np.add.at(recomposed, indices, weighted - weights * e_h[indices])
                matrix = stack["local"].blocks[block_index]["matrix"]
                local_d = matrix.createVecRight()
                local_d_image = matrix.createVecLeft()
                local_e = matrix.createVecRight()
                local_e_image = matrix.createVecLeft()
                try:
                    local_d.array[:] = di
                    matrix.mult(local_d, local_d_image)
                    local_e.array[:] = e_h[indices]
                    matrix.mult(local_e, local_e_image)
                    D_i_d_i = np.asarray(
                        local_d_image.array, dtype=np.complex128,
                    ).copy()
                    D_i_R_i_e_h = np.asarray(
                        local_e_image.array, dtype=np.complex128,
                    ).copy()
                    ell = np.asarray(
                        D_i_d_i - h[indices], dtype=np.complex128,
                    )
                    chi = np.asarray(
                        A_eh[indices] - D_i_R_i_e_h, dtype=np.complex128,
                    )
                    remainder_lhs = np.asarray(
                        D_i_d_i - D_i_R_i_e_h,
                        dtype=np.complex128,
                    )
                    remainder_rhs = chi + r_ref[indices] + ell
                    local_scale = max(
                        np.linalg.norm(local_d_image.array) + np.linalg.norm(h[indices]),
                        np.finfo(float).tiny,
                    )
                    local_solve_relative = float(np.linalg.norm(ell) / local_scale)
                    remainder_relative = _operation_relative(
                        remainder_lhs, remainder_rhs,
                        remainder_lhs, remainder_rhs, chi, r_ref[indices], ell,
                    )
                finally:
                    local_e_image.destroy()
                    local_e.destroy()
                    local_d_image.destroy()
                    local_d.destroy()
                if not np.isfinite(local_solve_relative) or not np.isfinite(remainder_relative):
                    all_local_gate = False
                if remainder_relative > 1.0e-10:
                    all_local_gate = False
                local_records.append({
                    "block_index": block_index,
                    "indices": indices.copy(),
                    "d_i": di.copy(),
                    "weighted_values": weighted.copy(),
                    "weights": weights.copy(),
                    "D_i_d_i": D_i_d_i,
                    "D_i_R_i_e_h": D_i_R_i_e_h,
                    "ell": ell,
                    "chi": chi,
                    "local_solve_relative": local_solve_relative,
                    "remainder_relative": remainder_relative,
                })
            pou_defect = float(np.max(np.abs(pou[p4_indices] - 1.0)))
            recomposition_relative = _operation_relative(
                recomposed, d - e_h, recomposed, d, e_h,
            )
            if pou_defect > 1.0e-12 or recomposition_relative > 1.0e-10:
                all_local_gate = False
            p2_facts = {
                "a": _array_summary(a), "h": _array_summary(h),
                "d": _array_summary(d), "t": _array_summary(t),
                "A_d": _array_summary(ad),
                "block_count": len(local_records),
                "e_h_A_identity_relative": eh_identity,
                "partition_of_unity_max_defect": pou_defect,
                "recomposition_relative": recomposition_relative,
                "r_ref_ratio": r_ref_ratio,
                "local_solve_max_relative": max(item["local_solve_relative"] for item in local_records),
                "local_remainder_max_relative": max(item["remainder_relative"] for item in local_records),
                "operation_scale": "sum of original lhs/rhs terms; cancellation-only denominators are not used",
                "bare_seconds": bare_seconds,
                "bare_apply_facts": bare_apply_facts,
                "bare_cost_delta": bare_cost_delta,
                "C_U": {
                    "action_identity": stack["p2_inverse"].action_identity,
                    "calls": int(bare_apply_facts.get("counts", {}).get("C", 0)),
                    "seconds": float(bare_apply_facts.get("operation_seconds", {}).get("C", 0.0)),
                },
                "balance": {
                    "initial": bare_apply_facts.get("initial", {}).get("constraint"),
                    "feedback": bare_apply_facts.get("feedback", {}),
                },
                "gate_pass": bool(
                    np.isfinite(eh_identity)
                    and eh_identity <= 1.0e-10
                    and pou_defect <= 1.0e-12
                    and recomposition_relative <= 1.0e-10
                    and all(item["remainder_relative"] <= 1.0e-10 for item in local_records)
                ),
            }

            p2_local_rows = max(
                int(np.asarray(block["indices"]).size) for block in blocks
            )
            p2_local_temporary_bytes = 8 * p2_local_rows * np.dtype(
                np.complex128
            ).itemsize
            check_live_workspace(
                label=f"{stem}:P2_local_records",
                resident=(
                    rhs, reference, r_ref, a, h, d, ad, t, A_a, A_eh,
                    e_h, pou, recomposed, p_columns_ind, blocks, local_records,
                    b4_vectors, md_observation,
                ),
                temporary_bytes=p2_local_temporary_bytes,
                rows=p2_local_rows,
                columns=1,
                weighted=False,
            )

            # Complete and atomically save P2 before constructing any fresh
            # P3 response arena.  A_t is a P2 prerequisite (the final
            # coarse-feedback term), so it is deliberately computed here.
            if reuse_input:
                A_t = _full_from_independent(n4, p4_indices, A_t_ind)
            else:
                a_t_started = time.perf_counter()
                try:
                    A_t = native_apply(t)
                finally:
                    current_timings["p3_A_t_seconds"] += time.perf_counter() - a_t_started
            a_ind = a[p4_indices]
            if not reuse_input:
                A_a_ind = A_a[p4_indices]
            d_ind = d[p4_indices]
            t_ind = t[p4_indices]
            A_t_ind = A_t[p4_indices]

            coarse_closure = {
                "initial": coarse_restriction_closure(
                    rhs, h, label=f"{stem}:C_U(g):g-Aa"
                ),
                "feedback": coarse_restriction_closure(
                    ad, ad - A_t, label=f"{stem}:C_U(A_d):A_d-A_t"
                ),
                "limit": 1.0e-8,
                "scale_definition": (
                    "PhysicalBalancedCoupling.balance: ||P_H residual|| / "
                    "(||P_H leading|| + ||P_H leading-P_H residual||)"
                ),
            }
            coarse_closure_gate = bool(
                all(
                    facts["finite"] and facts["relative"] <= coarse_closure["limit"]
                    for facts in (coarse_closure["initial"], coarse_closure["feedback"])
                )
            )
            p2_facts["coarse_closure"] = coarse_closure
            p2_facts["coarse_closure_gate"] = coarse_closure_gate
            p2_facts["C_U"]["bottom_facts"] = deepcopy(
                bare_apply_facts.get("bottom_facts", {})
            )
            if not coarse_closure_gate:
                all_local_gate = False
                p2_facts["gate_pass"] = False

            p_i_euclidean_norms = [
                float(np.linalg.norm(column)) for column in p_columns_ind.T
            ]
            p_i_curl_squared: list[float] = []
            p_i_curl_started = time.perf_counter()
            try:
                for local_column in range(p_columns_ind.shape[1]):
                    p_column_full = _full_from_independent(
                        n4, p4_indices, p_columns_ind[:, local_column],
                    )
                    metric_image = pullback_metric_action(p_column_full, "curl")
                    metric_value = float(np.real(np.vdot(
                        p_columns_ind[:, local_column], metric_image,
                    )))
                    scale = max(
                        np.linalg.norm(p_columns_ind[:, local_column])
                        * np.linalg.norm(metric_image), np.finfo(float).tiny,
                    )
                    if not np.isfinite(metric_value) or metric_value < -1.0e-10 * scale:
                        raise ValueError(f"{stem} local p_i curl metric is not positive")
                    p_i_curl_squared.append(max(metric_value, 0.0))
            finally:
                current_timings["p2_42_p_i_curl_seconds"] += time.perf_counter() - p_i_curl_started
            p_i_recomposition_relative = _operation_relative(
                np.sum(p_columns_ind, axis=1), d_ind,
                np.sum(p_columns_ind, axis=1), d_ind,
            )

            zero_rhs_norm = float(np.linalg.norm(rhs_ind))
            zero_initial_candidate = {
                "label": "P2_c_ref_zero_initial",
                "stage": "c_ref",
                "field_role": "zero_initial_guess",
                "rho": float(
                    zero_rhs_norm / max(zero_rhs_norm, np.finfo(float).tiny)
                ),
                "mass_squared": float(reference_mass_squared),
                "curl_squared": float(reference_curl_squared),
                "reference_mass_squared": float(reference_mass_squared),
                "reference_curl_squared": float(reference_curl_squared),
                "mass_error_norm": float(np.sqrt(max(reference_mass_squared, 0.0))),
                "curl_error_norm": float(np.sqrt(max(reference_curl_squared, 0.0))),
                "reference_mass_norm": float(np.sqrt(max(reference_mass_squared, 0.0))),
                "reference_curl_norm": float(np.sqrt(max(reference_curl_squared, 0.0))),
                "eta": 1.0,
                "eta_curl": 1.0,
                "residual_norm": zero_rhs_norm,
                "finite": bool(
                    np.isfinite(zero_rhs_norm)
                    and np.isfinite(reference_mass_squared)
                    and np.isfinite(reference_curl_squared)
                ),
            }
            p2_stage_candidates = {
                "c_ref": zero_initial_candidate,
                "a": evaluate_candidate(
                    "P2_a", a, A_a[p4_indices], rhs, reference,
                    reference_mass_squared, reference_curl_squared,
                ),
                "a_plus_d": evaluate_candidate(
                    "P2_a_plus_d", a + d, (A_a + ad)[p4_indices], rhs, reference,
                    reference_mass_squared, reference_curl_squared,
                ),
                "a_plus_d_minus_t": evaluate_candidate(
                    "P2_a_plus_d_minus_t", a + d - t,
                    (A_a + ad - A_t)[p4_indices], rhs, reference,
                    reference_mass_squared, reference_curl_squared,
                ),
            }
            d_mass_squared = pullback_metric_square(d, "mass")
            d_curl_squared = pullback_metric_square(d, "curl")
            a_mass_squared = pullback_metric_square(a, "mass")
            a_curl_squared = pullback_metric_square(a, "curl")
            t_mass_squared = pullback_metric_square(t, "mass")
            t_curl_squared = pullback_metric_square(t, "curl")
            correction = a + d - t
            correction_mass_squared = pullback_metric_square(correction, "mass")
            correction_curl_squared = pullback_metric_square(correction, "curl")
            d_minus_eh = d - e_h
            d_minus_eh_mass_squared = pullback_metric_square(d_minus_eh, "mass")
            d_minus_eh_curl_squared = pullback_metric_square(d_minus_eh, "curl")

            def metric_norm_record(mass_squared: float, curl_squared: float) -> dict[str, float]:
                return {
                    "mass_squared": float(mass_squared),
                    "curl_squared": float(curl_squared),
                    "mass_norm": float(np.sqrt(max(mass_squared, 0.0))),
                    "curl_norm": float(np.sqrt(max(curl_squared, 0.0))),
                }

            global_physical_norms = {
                "a": metric_norm_record(a_mass_squared, a_curl_squared),
                "d": metric_norm_record(d_mass_squared, d_curl_squared),
                "t": metric_norm_record(t_mass_squared, t_curl_squared),
                "d_minus_eh": metric_norm_record(
                    d_minus_eh_mass_squared, d_minus_eh_curl_squared,
                ),
                "a_plus_d_minus_t": metric_norm_record(
                    correction_mass_squared, correction_curl_squared,
                ),
            }
            for metric_name in ("mass", "curl"):
                term_norm_sum = sum(
                    global_physical_norms[name][f"{metric_name}_norm"]
                    for name in ("a", "d", "t")
                )
                correction_norm = global_physical_norms["a_plus_d_minus_t"][
                    f"{metric_name}_norm"
                ]
                global_physical_norms[f"{metric_name}_cancellation"] = {
                    "term_norm_sum": float(term_norm_sum),
                    "combined_norm": float(correction_norm),
                    "combined_over_term_sum": float(
                        correction_norm / max(term_norm_sum, np.finfo(float).tiny)
                    ),
                }
                eh_norm = global_physical_norms["d_minus_eh"][f"{metric_name}_norm"]
                global_physical_norms[f"{metric_name}_d_minus_eh"] = {
                    "combined_norm": float(eh_norm),
                    "reference": "d-e_h; local recomposition identity",
                }
            p2_facts["p_i_euclidean_norms"] = p_i_euclidean_norms
            p2_facts["p_i_sum_norm_over_d_norm"] = float(
                sum(p_i_euclidean_norms)
                / max(float(np.linalg.norm(d_ind)), np.finfo(float).tiny)
            )
            p2_facts["stage_errors"] = p2_stage_candidates
            p2_facts["d_global_mass_squared"] = d_mass_squared
            p2_facts["global_physical_norms"] = global_physical_norms
            p2_facts["stage_metric_gate"] = bool(
                all(item["finite"] for item in p2_stage_candidates.values())
                and np.isfinite(d_mass_squared)
            )
            p2_facts["p_i_original_mass_squared"] = None
            p2_facts["p_i_original_mass_status"] = (
                "deferred_to_P3_weighted_mgs_original_mass_energy"
            )
            p2_facts["p_i_curl_squared"] = p_i_curl_squared
            p2_facts["p_i_recomposition_relative"] = p_i_recomposition_relative
            p2_facts["p_i_original_mass_energy_sum"] = None
            p2_facts["p_i_curl_energy_sum"] = float(sum(p_i_curl_squared))
            p2_facts["p_i_mass_to_d_mass_ratio"] = None
            p2_facts["p_i_curl_to_d_curl_ratio"] = float(
                sum(p_i_curl_squared) / max(d_curl_squared, np.finfo(float).tiny)
            )
            if not p2_facts["stage_metric_gate"] or p_i_recomposition_relative > 1.0e-10:
                all_local_gate = False
            p2_facts["gate_pass"] = bool(
                p2_facts["gate_pass"]
                and p2_facts["stage_metric_gate"]
                and p_i_recomposition_relative <= 1.0e-10
            )
            p2_facts["p_i_count"] = 42
            p2_facts["p_i_coordinate_system"] = "p4_independent"
            p2_facts["A_t"] = _array_summary(A_t)
            p2_facts["reused_01"] = bool(reuse_input)
            p2_facts["continuation_action_counts"] = dict(current_counts)
            p2_facts["continuation_timings"] = dict(current_timings)
            p2_facts["atomic_save_order"] = "P2 packet completes before P3 response arena/selector"
            save(f"{stem}_p2_observation", {
                "stem": stem, "rhs_values": rhs, "reference_values": reference,
                "r_ref_values": r_ref, "a_values": a, "h_values": h,
                "d_values": d, "A_d_values": ad, "t_values": t,
                "A_a_values": A_a, "A_t_values": A_t,
                "local_blocks": local_records, "facts": p2_facts,
            })
            # The large per-block records are now hash-bound in P2.  Keep the
            # LS resident estimate honest while P3 owns the response arenas.
            del local_records
            # Release the captured B4/MD source graph and the temporary local
            # aliases immediately after the atomic P2 save.  The scalar P2
            # facts and the global vectors below are the only continuation
            # inputs still required.
            del blocks, b4_vectors, md_observation, pou, recomposed, A_eh, e_h
            del reference_a4, r_ref
            del weighted, weights, di, indices, block, matrix
            del local_d, local_d_image, local_e, local_e_image
            del D_i_d_i, D_i_R_i_e_h, ell, chi, remainder_lhs, remainder_rhs
            del source_block
            p2_background = ()

            # Own one pair of 48-column arenas for the rest of P3.  The
            # response packet is written from views into these arenas, so the
            # 42 p_i and A p_i families are not duplicated by a second L/AL
            # allocation.
            z_columns = int(Z_ind.shape[1])
            L_column_count = int(z_columns + 1 + 42 + 1)
            # Store response columns in Fortran order so each column family
            # remains a contiguous view for the QR/SVD kernels; otherwise a
            # selector call would allocate another full 42-column copy.
            L_ind = np.empty(
                (p4_indices.size, L_column_count),
                dtype=np.complex128,
                order="F",
            )
            AL_ind = np.empty_like(L_ind, order="F")
            L_ind[:, :z_columns] = Z_ind
            L_ind[:, z_columns] = a_ind
            L_ind[:, z_columns + 1:z_columns + 1 + 42] = p_columns_ind
            L_ind[:, -1] = -t_ind
            AL_ind[:, :z_columns] = Q_ind
            AL_ind[:, z_columns] = A_a_ind
            AL_ind[:, -1] = -A_t_ind
            p_columns_ind = L_ind[:, z_columns + 1:z_columns + 1 + 42]
            p_images_ind = AL_ind[:, z_columns + 1:z_columns + 1 + 42]
            p3_resident = (
                rhs, reference, actual, a, h, d, ad, t, A_a, A_t,
                rhs_ind, reference_ind, Z_ind, Q_ind,
                a_ind, d_ind, t_ind, A_a_ind, A_t_ind,
                L_ind, AL_ind, p_columns_ind, p_images_ind,
            )

            # P3 counts every local A p_i image, even if the reference-free
            # selector eventually keeps only eight of them.  Reused 01
            # images are already hash-bound; only 02/09 build these arenas.
            if reuse_input:
                p_images_ind[:, :] = np.asarray(
                    p_images_source, dtype=np.complex128,
                )
            else:
                p3_images_started = time.perf_counter()
                try:
                    for local_column in range(p_columns_ind.shape[1]):
                        p_column_full = np.zeros(n4, dtype=np.complex128)
                        p_column_full[p4_indices] = p_columns_ind[:, local_column]
                        p_image_full = native_apply(p_column_full)
                        p_images_ind[:, local_column] = p_image_full[p4_indices]
                        del p_column_full, p_image_full
                finally:
                    current_timings["p3_42_Ap_i_seconds"] += time.perf_counter() - p3_images_started
            if reuse_input:
                selected_indices = [int(index) for index in np.asarray(
                    reuse_p3["selected_indices"], dtype=np.int64,
                )]
                selector_facts = {
                    "reuse": True,
                    "old_selector_indices": selected_indices,
                    "source": reuse_packets["evidence"][1],
                }
            else:
                checkpoint(f"before_selector:{stem}")
                selector_base_images = np.column_stack((A_a_ind, -A_t_ind))
                check_ls_workspace(
                    rhs_ind.size, 10, weighted=False,
                    label=f"{stem}:P3_selector_rank_basis",
                    # The selector uses two anchor images but its iterative
                    # rank basis can retain up to max_local+2 columns.  Use
                    # the full ten-column bound and the same complete P3
                    # resident set later supplied to the selected solve.
                    resident=p3_resident + (selector_base_images,),
                    background=p2_background,
                )
                selector_started = time.perf_counter()
                try:
                    selected_indices, selector_facts = select_local_response_indices(
                        rhs_ind,
                        selector_base_images,
                        p_images_ind,
                        max_local=8, rtol=RANK_RTOL,
                    )
                finally:
                    if current_timings is not None:
                        current_timings["selector_seconds"] += time.perf_counter() - selector_started
                del selector_base_images
            if (
                len(selected_indices) > 8
                or len(set(selected_indices)) != len(selected_indices)
                or any(index < 0 or index >= 42 for index in selected_indices)
            ):
                raise ValueError(f"{stem} selected local response indices are invalid")
            selected_columns_ind = np.column_stack(
                (a_ind, p_columns_ind[:, selected_indices], -t_ind),
            )
            selected_images_ind = np.column_stack(
                (A_a_ind, p_images_ind[:, selected_indices], -A_t_ind),
            )
            selected_y, selected_facts = solve_svd(
                selected_images_ind, rhs_ind, label=f"{stem}:P3_selected",
                resident=p3_resident + (selected_columns_ind, selected_images_ind),
                background=p2_background,
            )
            selected_values_ind = selected_columns_ind @ selected_y
            selected_applied_ind = selected_images_ind @ selected_y
            response_packet_name = f"{stem}_p3_response_columns"
            save(response_packet_name, {
                "stem": stem,
                "coordinate_map": "p4_independent",
                "p4_indices": p4_indices,
                "p_columns_values": p_columns_ind,
                "p_images_values": p_images_ind,
                "A_a_values": A_a_ind,
                "A_t_values": A_t_ind,
                "selected_indices": selected_indices,
            })
            if reuse_input:
                reuse_packets["packets"].pop(
                    "A2R160_BAL_H_p4_01_p3_response_columns", None,
                )
                reuse_packets["p3"] = None
                reuse_p3 = None
                gc.collect()
            p_columns_source = None
            p_images_source = None
            A_a_source = None
            A_t_source = None

            # The full p_i arrays have been hash-bound to the response packet;
            # release them before the 48-column solves so the live-set check
            # covers the independent L/AL pair plus the actual solve buffers.
            del p_columns_ind, p_images_ind
            gc.collect()
            solve_resident = (
                p3_resident + (selected_columns_ind, selected_images_ind)
            )
            L_field_y = L_field_facts = None
            L_field_values_ind = L_field_applied_ind = None
            if metric_gate:
                L_field_y, L_field_facts = solve_weighted(
                    L_ind, reference_ind, label=f"{stem}:P3_field",
                    resident=solve_resident,
                    background=p2_background,
                )
                L_field_values_ind = L_ind @ L_field_y
                L_field_applied_ind = AL_ind @ L_field_y
            L_residual_y, L_residual_facts = solve_svd(
                AL_ind, rhs_ind, label=f"{stem}:P3_residual",
                resident=solve_resident,
                background=p2_background,
            )
            L_residual_values_ind = L_ind @ L_residual_y
            L_residual_applied_ind = AL_ind @ L_residual_y
            p3_candidates = {
                "L_residual": evaluate_candidate(
                    "L_residual", _full_from_independent(n4, p4_indices, L_residual_values_ind),
                    L_residual_applied_ind, rhs, reference,
                    reference_mass_squared, reference_curl_squared,
                ),
                "L_selected": evaluate_candidate(
                    "L_selected", _full_from_independent(n4, p4_indices, selected_values_ind),
                    selected_applied_ind, rhs, reference,
                    reference_mass_squared, reference_curl_squared,
                ),
            }
            if L_field_values_ind is not None and L_field_applied_ind is not None:
                p3_candidates["L_field"] = evaluate_candidate(
                    "L_field", _full_from_independent(n4, p4_indices, L_field_values_ind),
                    L_field_applied_ind, rhs, reference,
                    reference_mass_squared, reference_curl_squared,
                )
            p_i_original_mass_squared = (
                None if L_field_facts is None else [
                    float(value)
                    for value in L_field_facts["original_mass_energy"][z_columns + 1:-1]
                ]
            )
            p3_metric_association = {
                "p_i_original_mass_squared": p_i_original_mass_squared,
                "p_i_original_mass_energy_sum": (
                    None if p_i_original_mass_squared is None
                    else float(sum(p_i_original_mass_squared))
                ),
                "source": "P3 weighted_mgs original_mass_energy; P2 did not add duplicate M0 actions",
            }
            L_contains_Z_gate = bool(
                p3_candidates["L_residual"]["rho"]
                <= candidate_facts["Z_residual"]["rho"] + 1.0e-9
            )
            if L_field_facts is not None and "Z_field" in candidate_facts:
                L_contains_Z_gate = L_contains_Z_gate and bool(
                    p3_candidates["L_field"]["eta"]
                    <= candidate_facts["Z_field"]["eta"] + 1.0e-9
                )
            if not L_contains_Z_gate:
                all_p3_gate = False
            save(f"{stem}_p3_local_directions", {
                "stem": stem,
                "response_packet": response_packet_name,
                "coordinate_map": "p4_independent",
                "selected_indices": selected_indices,
                "selected_y": selected_y,
                "L_residual_y": L_residual_y,
                "L_field_y": L_field_y,
                "facts": {
                    "L_column_count": L_column_count,
                    "L_residual": L_residual_facts,
                    "L_field": L_field_facts,
                    "selector": selector_facts,
                    "selected_solve": selected_facts,
                    "p2_metric_association": p3_metric_association,
                    "contains_Z": {
                        "gate": L_contains_Z_gate,
                        "limit": 1.0e-9,
                        "description": "L contains Z and cannot worsen the best residual/field metric beyond roundoff",
                    },
                },
            })
            candidates = {**candidate_facts, **p3_candidates}
            old_difference = _relative(actual, old_solution)
            input_counts = dict(current_counts)
            input_counts["B4_total"] = int(observed_count + 1)
            input_elapsed = time.perf_counter() - input_start
            input_summary = {
                "ordinal": ordinal,
                "stem": stem,
                "elapsed_seconds": float(input_elapsed),
                "old_control_packet": str(old_path),
                "old_control_packet_sha256": hashlib.sha256(old_path.read_bytes()).hexdigest(),
                "old_solution_difference": old_difference,
                "fresh_reference_A4_bridge_relative": reference_bridge,
                "r_ref_ratio": r_ref_ratio,
                "r_ref_gate": r_ref_gate,
                "I4": {
                    "facts": {
                        **i4_facts,
                        "cost_delta": i4_cost_delta,
                        "actual_applied_plus_residual_relative": actual_identity,
                        "actual_native_A4_vs_applied_relative": actual_native_identity,
                        "actual_i4_consistency_gate": actual_i4_consistency_gate,
                    },
                    "counted_pc_outputs": observed_count,
                    "capture_gate": capture_gate,
                    "Z_columns": int(Z_ind.shape[1]),
                    "observed_pc_ordinals": observed_ordinals,
                },
                "P1": {
                    **p1_facts,
                },
                "P2": p2_facts,
                "P3": {
                    "candidate_count": L_column_count,
                    "selected_local_indices": [int(index) for index in selected_indices],
                    "selector": selector_facts,
                    "contains_Z_gate": L_contains_Z_gate,
                    "candidates": p3_candidates,
                },
                "candidates": candidates,
                "counts": input_counts,
                "timings": dict(current_timings or {}),
                "workspace_bound": dict(workspace_peak),
                "gates": {
                    "capture": capture_gate and capture_md_gate,
                    "mapping": bool(reference_bridge <= 1.0e-10 and r_ref_gate),
                    "metric": bool(metric_gate and metric_equivalence <= 1.0e-10),
                    "p1": bool(actual_i4_consistency_gate and reconstruction_gate and min_rho_gate),
                    "local_identity": bool(p2_facts["gate_pass"]),
                    "p2_stage_metric": bool(p2_facts["stage_metric_gate"]),
                    "p3_contains_Z": L_contains_Z_gate,
                },
            }
            summary["inputs"].append(input_summary)
            summary["counts"]["A4"] += current_counts["A4"]
            summary["counts"]["M0_pullback"] += current_counts["M0_pullback"]
            summary["counts"]["curl_pullback"] += current_counts["curl_pullback"]
            summary["counts"]["M0_direct_degree4"] += current_counts["M0_direct_degree4"]
            summary["counts"]["curl_direct_degree4"] += current_counts["curl_direct_degree4"]
            summary["counts"]["P64_primal"] += current_counts["P64_primal"]
            summary["counts"]["P64_adjoint"] += current_counts["P64_adjoint"]
            checkpoint(f"input_complete:{stem}")
            # Checkpoint while the input clock is still live so the per-input
            # budget is applied to the complete recorded input, including the
            # final packet/summary construction above.
            input_start = None
            current_counts = None
            current_timings = None
            del p3_resident, solve_resident, L_ind, AL_ind
            del selected_columns_ind, selected_images_ind
            del L_field_values_ind, L_field_applied_ind
            del L_residual_values_ind, L_residual_applied_ind
            del selected_values_ind, selected_applied_ind
            del Z_ind, Q_ind, actual
            if reuse_input:
                reuse_packets["packets"].pop("p0_metric_equivalence", None)
                reuse_packets["p0"] = None
                reuse_packets["packets"].clear()
                gc.collect()
            gc.collect()

        summary["stage_times"]["diagnosis_seconds"] = time.perf_counter() - controls_start
        summary["metric_equivalence"] = metric_equivalence_records
        summary["workspace_bound"] = dict(workspace_peak)
        summary["gates"].update(
            mapping=all_mapping_gate,
            metric=metric_gate,
            capture=all_capture_gate,
            local_identities=all_local_gate,
            p1=all_p1_gate,
            p3=all_p3_gate,
            source_clean=True,
            input_count=len(summary["inputs"]) == 3,
        )
        summary["gates"]["p0"] = True

        by_input = {item["stem"]: item["candidates"] for item in summary["inputs"]}

        def candidate(name: str, stem: str) -> dict[str, Any] | None:
            return by_input.get(stem, {}).get(name)

        def strong_signal(name: str) -> bool:
            difficult = [candidate(name, "A2R160_BAL_H_p4_01"),
                         candidate(name, "LIGHT448_BAL_H_p4_09")]
            g2 = candidate(name, "A2R160_BAL_H_p4_02")
            actuals = {
                stem: candidate("actual", stem)
                for stem in selected_stems
            }
            if any(value is None for value in difficult) or g2 is None:
                return False
            if any(actuals[stem] is None for stem in selected_stems):
                return False
            if any(value.get("eta") is None or actuals[stem].get("eta") is None
                   or value["eta"] > 0.5 * actuals[stem]["eta"]
                   for value, stem in zip(difficult, (selected_stems[0], selected_stems[2]), strict=True)):
                return False
            if g2.get("eta") is None or actuals[selected_stems[1]].get("eta") is None:
                return False
            if g2["eta"] > 1.10 * actuals[selected_stems[1]]["eta"]:
                return False
            for stem in selected_stems:
                value = candidate(name, stem)
                actual_value = actuals[stem]
                if (value is None or value.get("rho") is None or actual_value.get("rho") is None
                        or value.get("eta_curl") is None or actual_value.get("eta_curl") is None
                        or value["rho"] > 1.10 * actual_value["rho"]
                        or value["eta_curl"] > 1.10 * actual_value["eta_curl"]):
                    return False
            return True

        d_strong = strong_signal("Z_dual_mass") if metric_gate else False
        s_strong = strong_signal("L_selected") if all_capture_gate and all_local_gate else False
        total_b4 = summary["counts"]["bare_B4"] + sum(
            int(item["I4"]["counted_pc_outputs"]) for item in summary["inputs"]
        )

        def action_count_gate(formal_elapsed: float) -> bool:
            counts = summary["counts"]
            return bool(
                counts["attempted_I4"] <= 3
                and counts["completed_I4"] <= 3
                and counts["new_I4"] <= 3
                and counts["attempted_B4"] <= 3
                and counts["completed_B4"] <= 3
                and counts["bare_B4"] <= 3
                and total_b4 <= 15
                and counts["A4"] <= 200
                and counts["M0_pullback"] + counts["M0_direct_degree4"] <= 240
                and counts["curl_pullback"] + counts["curl_direct_degree4"] <= 240
                and formal_elapsed <= P4_DIAGNOSIS_WORKFLOW_SECONDS
            )

        # The continuation clock is the formal workflow budget.  The old
        # formal/checker charge is carried separately and is never replaced by
        # the worker's local perf_counter wall value.
        update_time_budget("preliminary_action_gate")
        formal_accounted_seconds = float(
            summary["time_budget"]["formal_accounted_seconds"]
        )
        summary["stage_times"]["total_seconds"] = time.perf_counter() - build_start
        summary["stage_times"]["formal_accounted_seconds"] = formal_accounted_seconds
        summary["counts"]["new_I4_attempted"] = (
            summary["counts"]["attempted_I4"] - prior_counts["I4"]
        )
        summary["counts"]["new_I4_completed"] = (
            summary["counts"]["completed_I4"] - prior_counts["I4"]
        )
        summary["counts"]["new_B4_attempted"] = (
            summary["counts"]["attempted_B4"] - prior_counts["bare_B4"]
        )
        summary["counts"]["new_B4_completed"] = (
            summary["counts"]["completed_B4"] - prior_counts["bare_B4"]
        )
        count_gate = action_count_gate(formal_accounted_seconds)
        summary["counts"]["total_B4"] = total_b4
        summary["gates"]["action_counts"] = count_gate

        def optional_seconds(value: Any) -> float | None:
            if value is None:
                return None
            try:
                result = float(value)
            except (TypeError, ValueError):
                return None
            return result if np.isfinite(result) and result >= 0.0 else None

        def timing_value(item: dict[str, Any], key: str) -> float | None:
            return optional_seconds(item.get("timings", {}).get(key))

        p3_Ap_i_seconds = [
            timing_value(item, "p3_42_Ap_i_seconds")
            for item in summary["inputs"]
        ]
        p3_A_t_seconds = [
            timing_value(item, "p3_A_t_seconds")
            for item in summary["inputs"]
        ]
        p2_p_i_curl_seconds = [
            timing_value(item, "p2_42_p_i_curl_seconds")
            for item in summary["inputs"]
        ]
        i4_seconds = []
        bare_seconds = []
        selector_qr_seconds = []
        for item in summary["inputs"]:
            i4_facts = item.get("I4", {}).get("facts", {})
            i4_cost = i4_facts.get("cost_delta", {})
            i4_seconds.append(
                None if i4_facts.get("timing_status")
                or i4_cost.get("timing_status") == "unknown"
                else optional_seconds(
                    i4_facts.get("actual_elapsed_seconds", i4_facts.get("seconds"))
                )
            )
            bare_seconds.append(optional_seconds(item.get("P2", {}).get("bare_seconds")))
            selector_qr_seconds.append(timing_value(item, "selector_seconds"))

        selective_per_input = [
            None if any(value is None for value in values) else float(sum(values))
            for values in zip(
                bare_seconds, p3_Ap_i_seconds, p3_A_t_seconds,
                selector_qr_seconds, strict=True,
            )
        ]
        dual_known = {
            stem: value for stem, value in zip(selected_stems, i4_seconds, strict=True)
            if value is not None
        }
        selective_known = {
            stem: value for stem, value in zip(
                selected_stems, selective_per_input, strict=True,
            )
            if value is not None
        }
        cost_basis_stems = [
            stem for stem in selected_stems[1:]
            if stem in dual_known and stem in selective_known
        ]
        dual_total = (
            float(sum(i4_seconds)) if all(value is not None for value in i4_seconds)
            else None
        )
        selective_total = (
            float(sum(selective_per_input))
            if all(value is not None for value in selective_per_input)
            else None
        )
        dual_known_total = float(sum(dual_known[stem] for stem in cost_basis_stems))
        selective_known_total = float(
            sum(selective_known[stem] for stem in cost_basis_stems)
        )
        cost_basis_complete = cost_basis_stems == list(selected_stems[1:])
        cost_screen = {
            "dual_mass_scaled": {
                "measured_i4_seconds_per_input": i4_seconds,
                "measured_total_seconds": dual_total,
                "measured_known_input_seconds": float(sum(dual_known.values())),
                "unknown_input_stems": [
                    stem for stem, value in zip(selected_stems, i4_seconds, strict=True)
                    if value is None
                ],
                "fixed_diagonal_scaling": "one additional vector scaling per Krylov metric action; not separately timed",
            },
            "selective_multiblock": {
                "measured_bare_B4_seconds_per_input": bare_seconds,
                "measured_all_42_Ap_i_seconds_per_input": p3_Ap_i_seconds,
                "measured_A_t_seconds_per_input": p3_A_t_seconds,
                "measured_selector_seconds_per_input": selector_qr_seconds,
                "measured_total_seconds": selective_total,
                "measured_known_input_seconds": float(sum(selective_known.values())),
                "unknown_input_stems": [
                    stem for stem, value in zip(
                        selected_stems, selective_per_input, strict=True,
                    ) if value is None
                ],
                "future_model": "one bare B4 plus all 42 A p_i images, A(-t), and reference-free selection/QR",
            },
            "comparison_basis": {
                "definition": "measured nested wall-clock seconds; fixed-D scaling is not assigned synthetic seconds",
                "complete_all_input_totals_available": (
                    dual_total is not None and selective_total is not None
                ),
                "qualified_common_input_stems": cost_basis_stems,
                "requires_02_and_09_measured": True,
                "02_and_09_complete": cost_basis_complete,
                "dual_known_common_seconds": dual_known_total,
                "selective_known_common_seconds": selective_known_total,
            },
        }
        if not all(summary["gates"].get(key, False) for key in (
                "p0", "mapping", "metric", "capture", "local_identities", "p1", "p3",
                "interface_structure",
                "input_count", "action_counts")):
            primary = "IMPLEMENTATION_OR_METRIC_REPAIR"
            confidence = "high"
        elif d_strong and s_strong:
            if (
                cost_basis_complete
                and np.isfinite(dual_known_total)
                and np.isfinite(selective_known_total)
                and selective_known_total < dual_known_total
            ):
                primary = "SELECTIVE_MULTIPRECONDITIONED_P4"
            else:
                primary = "DUAL_MASS_SCALED_P4_KRYLOV"
            confidence = "high"
        elif d_strong:
            primary = "DUAL_MASS_SCALED_P4_KRYLOV"
            confidence = "high"
        elif s_strong:
            primary = "SELECTIVE_MULTIPRECONDITIONED_P4"
            confidence = "high"
        else:
            primary = "PHYSICAL_INTERFACE_MULTILEVEL_REDESIGN"
            confidence = "medium"
        summary["decision"] = {
            "primary_method": primary,
            "confidence": confidence,
            "dual_mass_strong_action_signal": d_strong,
            "selective_strong_action_signal": s_strong,
            "strong_signal_definition": {
                "difficult_inputs": [selected_stems[0], selected_stems[2]],
                "difficult_eta_factor_max": 0.5,
                "g2_eta_factor_max": 1.10,
                "all_eta_curl_factor_max": 1.10,
                "all_rho_factor_max": 1.10,
            },
            "reference_role": "measurement_only; not used by I4, B4, or selector",
            "measured_cost_comparison": cost_screen,
            "counterevidence": {
                "best_L_oracle": {
                    stem: by_input[stem].get("L_field") for stem in selected_stems
                },
                "selected_reference_free": {
                    stem: by_input[stem].get("L_selected") for stem in selected_stems
                },
            },
            "next_method_cost_screen": {
                "dual_mass_scaled": {
                    "new_A4": 0,
                    "new_pullback_M0_per_apply": 0,
                    "per_apply_diagonal_scaling": 1,
                    "fixed_D_from_direct_degree4": True,
                    "measured_i4_seconds_per_input": i4_seconds,
                    "measured_total_seconds": cost_screen["dual_mass_scaled"]["measured_total_seconds"],
                },
                "selective_multiblock": {
                    "new_A4_images": 43,
                    "selected_local_cap": 8,
                    "measured_bare_B4_seconds_per_input": bare_seconds,
                    "measured_all_42_Ap_i_seconds_per_input": p3_Ap_i_seconds,
                    "measured_A_t_seconds_per_input": p3_A_t_seconds,
                    "measured_selector_seconds_per_input": selector_qr_seconds,
                    "measured_all_42_p_i_curl_seconds_per_input": p2_p_i_curl_seconds,
                    "measured_total_seconds": cost_screen["selective_multiblock"]["measured_total_seconds"],
                },
                "tie_rule": "if both pass, choose the lower measured action family; fixed D adds no new pullback M0 action",
            },
            "interface_blueprint": summary["interface_blueprint"],
        }
        summary["stage_times"]["summary_construction_seconds"] = (
            time.perf_counter() - build_start - summary["stage_times"]["total_seconds"]
        )
        # Charge the final summary construction on the same dual-clock budget
        # used by every safe point.  The formal gate is based on this carried
        # charge, not on a local perf_counter value that omits the old run.
        update_time_budget("final_summary")
        formal_accounted_seconds = float(
            summary["time_budget"]["formal_accounted_seconds"]
        )
        summary["stage_times"]["total_seconds"] = time.perf_counter() - build_start
        summary["stage_times"]["formal_accounted_seconds"] = formal_accounted_seconds
        summary["gates"]["action_counts"] = action_count_gate(formal_accounted_seconds)
        all_gate_pass = bool(
            all(summary["gates"].get(key, False) for key in (
                "p0", "mapping", "metric", "capture", "local_identities", "p1", "p3",
                "interface_structure",
                "input_count", "action_counts",
            ))
        )
        summary.update(
            status=(
                "P4_DIRECTION_DIAGNOSIS_COMPLETED"
                if all_gate_pass else "P4_DIRECTION_DIAGNOSIS_GATED_FAILURE"
            ),
            gate_pass=all_gate_pass,
        )
        save("p4_direction_diagnosis_v13", summary)
        save("p4_direction_summary", summary)
        return summary
    except BaseException as exc:
        summary["stage_times"]["total_seconds"] = time.perf_counter() - build_start
        summary.update(
            status="P4_DIRECTION_DIAGNOSIS_FAILED",
            gate_pass=False,
            exception_type=type(exc).__name__,
            exception=str(exc),
        )
        save("p4_direction_diagnosis_v13", summary)
        save("p4_direction_summary", summary)
        raise
    finally:
        if metric6 is not None:
            metric6.destroy()
        if metric4 is not None:
            metric4.destroy()
        if stack is not None:
            destroy_macro_stack(stack)


__all__ = ["run_macro_m1_controls", "run_p4_direction_diagnosis"]
