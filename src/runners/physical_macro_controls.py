"""Small M1 controls for the Review V10 physical macro inverse.

The runner deliberately owns only orchestration and evidence.  The local
operator, bounded I4 policy, transfers, and metrics remain in the reusable
solver modules.  Frozen G0 packets are read through the existing audited
loader; no reference operator or solve is rebuilt here.
"""

from __future__ import annotations

import hashlib
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


__all__ = ["run_macro_m1_controls"]
