"""Selected same-mesh p6 physical Maxwell action and recovery helpers.

The positive p6/p3/p1 bundle remains the auxiliary preconditioner.  This
module adds only the physical p6 volume form and the streaming Fourier-DtN
action on the very same mesh, without assembling a p6 matrix or creating a
physical KSP.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import time
from typing import Any

import numpy as np


PHYSICAL_BUNDLE_SCHEMA = "task038.same_mesh_hcurl_pmg.physical.v2"
PHYSICAL_PROFILE = "same_mesh_hcurl_pmg_v1_requalified"


def _notify_stage(
    callback: Callable[[str, Mapping[str, Any]], None] | None,
    name: str,
    facts: Mapping[str, Any],
) -> None:
    if callback is not None:
        callback(name, dict(facts))


def _surface_assemblers(
    function_space: Any,
    mesh_data: Any,
    cfg: Any,
    qdegree: int,
    *,
    jit_options: Mapping[str, Any] | None = None,
    dtn_phase_gauge: str = "global_z",
    verify_dtn_quadrature: bool = False,
    collect_timing: bool = False,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[tuple[str, int], Any]:
    from .dtn_port_3d import _ReusableSurfaceComponentAssembler
    from .dtn_boundary_phase_gauge import BOUNDARY_PLANE, validate_phase_gauge

    validate_phase_gauge(dtn_phase_gauge)

    if progress_callback is not None and not callable(progress_callback):
        raise TypeError("surface assembler progress callback must be callable")
    result = {}
    targets = tuple((side, component) for side in ("top", "bottom") for component in (0, 1))
    for completed, (side, component) in enumerate(targets, start=1):
        started = time.perf_counter()
        cpu_started = time.process_time()
        base = {
            "phase": "surface_form_jit",
            "side": str(side),
            "component": int(component),
            "completed": completed - 1,
            "total": len(targets),
            "quadrature_degree": int(qdegree),
        }
        if progress_callback is not None:
            progress_callback({**base, "status": "STARTED"})
        try:
            result[(side, component)] = _ReusableSurfaceComponentAssembler(
                function_space,
                mesh_data,
                cfg.tags.z_max if side == "top" else cfg.tags.z_min,
                component,
                quadrature_degree=qdegree,
                jit_options=jit_options,
                boundary_reference_z=(
                    float(cfg.physical_z_max if side == "top" else cfg.physical_z_min)
                    if dtn_phase_gauge == BOUNDARY_PLANE else None
                ),
                verify_compiled_gauss=verify_dtn_quadrature,
                collect_timing=collect_timing,
            )
        except BaseException as error:
            if progress_callback is not None:
                progress_callback({
                    **base,
                    "status": "FAILED",
                    "completed": completed - 1,
                    "elapsed_seconds": max(0.0, time.perf_counter() - started),
                    "process_cpu_seconds": max(0.0, time.process_time() - cpu_started),
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                })
            raise
        if progress_callback is not None:
            progress_callback({
                **base,
                "status": "COMPLETE",
                "completed": completed,
                "elapsed_seconds": max(0.0, time.perf_counter() - started),
                "process_cpu_seconds": max(0.0, time.process_time() - cpu_started),
            })
    return result


def _native_array_sha256(value: Any) -> str:
    import hashlib

    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def _task41_verify_compiled_native_quadrature(
    production_assemblers: Mapping[tuple[str, int], Any], quadrature_degree: int
) -> dict[str, Any]:
    """Require actual compiled FFCx facet rules to equal the native tensor rule."""

    import basix

    degree = int(quadrature_degree)
    interval_points, interval_weights = basix.make_quadrature(
        basix.CellType.interval, degree
    )
    facet_points, facet_weights = basix.make_quadrature(
        basix.CellType.quadrilateral, degree
    )
    if not len(interval_points) or facet_points.ndim != 2 or facet_points.shape[1] != 2:
        raise ValueError("Task41 native/compiled quadrature has an unsupported rule shape")
    expected_pairs = {
        (float(x[0]), float(y[0])): float(wx * wy)
        for x, wx in zip(interval_points, interval_weights, strict=True)
        for y, wy in zip(interval_points, interval_weights, strict=True)
    }
    if len(expected_pairs) != len(interval_points) ** 2:
        raise ValueError("Task41 native tensor quadrature contains duplicate nodes")
    for point, weight in zip(facet_points, facet_weights, strict=True):
        expected_weight = expected_pairs.get((float(point[0]), float(point[1])))
        if expected_weight is None or not np.isclose(
            float(weight), expected_weight, rtol=32 * np.finfo(float).eps, atol=0.0
        ):
            raise ValueError("Basix quadrilateral rule is not the native interval tensor product")

    def signature(array: Any) -> dict[str, Any]:
        contiguous = np.ascontiguousarray(array)
        return {
            "shape": tuple(contiguous.shape),
            "dtype": str(contiguous.dtype),
            "sha256": _native_array_sha256(contiguous),
        }

    expected_points = signature(facet_points)
    expected_weights = signature(facet_weights)
    checked_rules = 0
    for key, assembler in production_assemblers.items():
        identity = getattr(assembler, "compiled_gauss_identity", None)
        if not isinstance(identity, Mapping) or not identity.get("rules"):
            raise ValueError(f"compiled Gauss identity is missing for surface {key}")
        for record in identity["rules"]:
            facet_cell = record.get("facet_cell")
            facet_cell_name = str(getattr(facet_cell, "name", facet_cell)).lower().split(".")[-1]
            if (
                int(record.get("degree", -1)) != degree
                or facet_cell_name != "quadrilateral"
                or record.get("points") != expected_points
                or record.get("weights") != expected_weights
            ):
                raise ValueError(
                    f"compiled FFCx nodes/weights differ from the native tensor Gauss rule for {key}"
                )
            checked_rules += 1
    if checked_rules != 4:
        raise ValueError("Task41 requires compiled quadrature verification for all four port components")
    return {
        "degree": degree,
        "facet_cell": "quadrilateral",
        "native_rule": "Basix interval Gauss-Legendre tensor product used by FacetPolynomial.integral_native",
        "compiled_rule_count": checked_rules,
        "compiled_nodes_and_weights_equal_native_tensor_product": True,
        "compiled_forms_include_actual_C_weight_and_node_id_checks": True,
    }


def _task41_native_probe_indices(modes: Any) -> tuple[int, ...]:
    """Select a tiny, finite two-port s/p pair plus a distinct wavevector per port."""

    groups: dict[str, dict[tuple[Any, ...], list[int]]] = {"bottom": {}, "top": {}}
    score_by_key: dict[tuple[str, tuple[Any, ...]], float] = {}
    k_by_key: dict[tuple[str, tuple[Any, ...]], tuple[complex, ...]] = {}
    for index, mode in enumerate(modes):
        side = str(mode.side)
        if side not in groups:
            continue
        key = (
            int(mode.m), int(mode.n), complex(mode.alpha), complex(mode.gamma),
            tuple(complex(value) for value in np.asarray(mode.k_vector).reshape(-1)),
        )
        groups[side].setdefault(key, []).append(index)
        wave_key = (side, key)
        score_by_key[wave_key] = float(np.hypot(abs(complex(mode.alpha)), abs(complex(mode.gamma))))
        k_by_key[wave_key] = key[-1]
    selected: set[int] = set()
    for side in ("bottom", "top"):
        side_groups = groups[side]
        if len(side_groups) < 2:
            raise ValueError(f"Task41 native pairing needs two distinct {side} wavevectors")
        paired = [
            key for key, indices in side_groups.items()
            if {str(getattr(modes[index], "polarization", "")).lower() for index in indices}
            >= {"s", "p"}
        ]
        if not paired:
            raise ValueError(f"Task41 native pairing needs an adjacent s/p {side} wavevector")
        near_key = min(paired, key=lambda key: (score_by_key[(side, key)], key[0], key[1]))
        near_k = k_by_key[(side, near_key)]
        other_keys = [
            key for key in side_groups
            if k_by_key[(side, key)] != near_k
        ]
        if not other_keys:
            raise ValueError(f"Task41 native pairing needs a distinct {side} wavevector")
        far_key = max(other_keys, key=lambda key: (score_by_key[(side, key)], key[0], key[1]))
        selected.update(side_groups[near_key])
        # One far mode tests a different wavevector without duplicating a full polarization pair.
        selected.add(side_groups[far_key][0])
    result = tuple(sorted(selected))
    coverage = {
        side: {
            str(getattr(modes[index], "polarization", "")).lower()
            for index in result if str(modes[index].side) == side
        }
        for side in ("bottom", "top")
    }
    if any(coverage[side] != {"s", "p"} for side in ("bottom", "top")):
        raise ValueError("Task41 native representative set does not cover s and p on both ports")
    return result


def _task41_compare_sparse_functional(
    reference: Any,
    candidate: Any,
    *,
    relative_tolerance: float,
) -> dict[str, Any]:
    """Compare full sparse functionals with the reference L2 norm as denominator."""

    ref_rows, ref_values = reference
    got_rows, got_values = candidate
    ref_rows = np.asarray(ref_rows)
    got_rows = np.asarray(got_rows)
    ref_values = np.asarray(ref_values, dtype=np.complex128)
    got_values = np.asarray(got_values, dtype=np.complex128)
    if (
        ref_rows.shape != ref_values.shape
        or got_rows.shape != got_values.shape
        or (len(ref_rows) > 1 and not np.all(ref_rows[:-1] < ref_rows[1:]))
        or (len(got_rows) > 1 and not np.all(got_rows[:-1] < got_rows[1:]))
    ):
        raise ValueError("Task41 pairing requires sorted unique rows and matching values")
    common, ref_positions, got_positions = np.intersect1d(
        ref_rows, got_rows, assume_unique=True, return_indices=True
    )
    ref_only = np.setdiff1d(ref_rows, got_rows, assume_unique=True)
    got_only = np.setdiff1d(got_rows, ref_rows, assume_unique=True)
    delta_common = ref_values[ref_positions] - got_values[got_positions]
    difference_squared = float(np.vdot(delta_common, delta_common).real)
    if len(ref_only):
        values = ref_values[np.searchsorted(ref_rows, ref_only)]
        difference_squared += float(np.vdot(values, values).real)
    if len(got_only):
        values = got_values[np.searchsorted(got_rows, got_only)]
        difference_squared += float(np.vdot(values, values).real)
    reference_norm = float(np.linalg.norm(ref_values))
    difference_norm = float(np.sqrt(max(0.0, difference_squared)))
    relative_error = (
        difference_norm / reference_norm
        if reference_norm > 0.0
        else (0.0 if difference_norm == 0.0 else float("inf"))
    )
    max_abs = float(np.max(np.abs(delta_common), initial=0.0))
    if len(ref_only):
        max_abs = max(max_abs, float(np.max(np.abs(ref_values[np.searchsorted(ref_rows, ref_only)]), initial=0.0)))
    if len(got_only):
        max_abs = max(max_abs, float(np.max(np.abs(got_values[np.searchsorted(got_rows, got_only)]), initial=0.0)))
    support_difference = int(len(ref_only) + len(got_only))
    return {
        "support_symmetric_difference_count": support_difference,
        "support_rows_equal": support_difference == 0,
        "reference_row_count": int(len(ref_rows)),
        "candidate_row_count": int(len(got_rows)),
        "reference_l2_norm": reference_norm,
        "difference_l2_norm": difference_norm,
        "relative_l2_error_over_reference_norm": relative_error,
        "maximum_absolute_difference_diagnostic_only": max_abs,
        "relative_tolerance": float(relative_tolerance),
        "pass": bool(support_difference == 0 and relative_error <= relative_tolerance),
    }


def _task41_pair_native_surface_assemblers(
    modes: Any,
    production_assemblers: Mapping[tuple[str, int], Any],
    native_assemblers: Mapping[tuple[str, int], Any],
    mpc: Any,
    cfg: Any,
    *,
    relative_tolerance: float,
    h_relative_tolerance: float = 1.0e-14,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Pair finite live B/D/H functionals, actions, cutoffs, and phase timings."""

    from .dtn_port_3d import (
        _combine_owned_entries,
        _mode_projection_denominator,
        _traction_vector,
    )
    from .dtn_boundary_phase_gauge import (
        BOUNDARY_PLANE,
        assembly_projection_denominator,
        phase_gauge_descriptor,
        port_plane_z,
    )

    selected = _task41_native_probe_indices(modes)
    comm = mpc.function_space.mesh.comm
    native_rule = next(iter(native_assemblers.values())).rule
    comparisons = []
    timing = {
        key: 0.0 for key in (
            "D_projection_production_wall_seconds", "D_projection_production_process_cpu_seconds",
            "D_projection_native_wall_seconds", "D_projection_native_process_cpu_seconds",
            "B_coupling_production_wall_seconds", "B_coupling_production_process_cpu_seconds",
            "B_coupling_native_wall_seconds", "B_coupling_native_process_cpu_seconds",
        )
    }
    alpha_test = 0.7 - 0.4j
    for index in selected:
        mode = modes[index]
        reference_components = []
        native_components = []
        component_checks = []
        component_cutoffs = []
        for component in (0, 1):
            old_assembler = production_assemblers[(str(mode.side), component)]
            new_assembler = native_assemblers[(str(mode.side), component)]
            started, cpu_started = time.perf_counter(), time.process_time()
            old_entries = old_assembler.assemble_entries(mode, mpc)
            old_elapsed, old_cpu = time.perf_counter() - started, time.process_time() - cpu_started
            started, cpu_started = time.perf_counter(), time.process_time()
            new_entries = new_assembler.assemble_entries(mode, mpc)
            new_elapsed, new_cpu = time.perf_counter() - started, time.process_time() - cpu_started
            component_check = _task41_compare_sparse_functional(
                old_entries, new_entries, relative_tolerance=relative_tolerance
            )
            component_check.update({
                "component": component,
                "production_wall_seconds": old_elapsed,
                "production_process_cpu_seconds": old_cpu,
                "native_wall_seconds": new_elapsed,
                "native_process_cpu_seconds": new_cpu,
            })
            component_checks.append(component_check)
            component_cutoffs.append({
                "component": component,
                "production": dict(old_assembler.assembly_stats.get("last_filter_audit", {})),
                "native": dict(new_assembler.rule.assembly_stats.get("last_component_filter", {})),
            })
            reference_components.append(old_entries)
            native_components.append(new_entries)

        traction = _traction_vector(mode, cfg)
        projection_coefficients = (mode.e_vector[0], mode.e_vector[1])
        coupling_coefficients = (-traction[0], -traction[1])
        combination_cutoffs = {}

        started, cpu_started = time.perf_counter(), time.process_time()
        reference_projection_audit: dict[str, Any] = {}
        reference_projection = _combine_owned_entries(
            tuple(reference_components), projection_coefficients,
            comm=comm, audit=reference_projection_audit,
        )
        reference_projection = (reference_projection[0], np.conjugate(reference_projection[1]))
        projection_reference_wall = time.perf_counter() - started
        projection_reference_cpu = time.process_time() - cpu_started
        started, cpu_started = time.perf_counter(), time.process_time()
        native_projection_audit: dict[str, Any] = {}
        native_projection = _combine_owned_entries(
            tuple(native_components), projection_coefficients,
            comm=comm, audit=native_projection_audit,
        )
        native_projection = (native_projection[0], np.conjugate(native_projection[1]))
        projection_native_wall = time.perf_counter() - started
        projection_native_cpu = time.process_time() - cpu_started
        projection_check = _task41_compare_sparse_functional(
            reference_projection, native_projection,
            relative_tolerance=relative_tolerance,
        )
        combination_cutoffs["D_projection"] = {
            "production": reference_projection_audit,
            "native": native_projection_audit,
        }
        timing["D_projection_production_wall_seconds"] += projection_reference_wall
        timing["D_projection_production_process_cpu_seconds"] += projection_reference_cpu
        timing["D_projection_native_wall_seconds"] += projection_native_wall
        timing["D_projection_native_process_cpu_seconds"] += projection_native_cpu

        started, cpu_started = time.perf_counter(), time.process_time()
        reference_coupling_audit: dict[str, Any] = {}
        reference_coupling = _combine_owned_entries(
            tuple(reference_components), coupling_coefficients,
            comm=comm, audit=reference_coupling_audit,
        )
        coupling_reference_wall = time.perf_counter() - started
        coupling_reference_cpu = time.process_time() - cpu_started
        started, cpu_started = time.perf_counter(), time.process_time()
        native_coupling_audit: dict[str, Any] = {}
        native_coupling = _combine_owned_entries(
            tuple(native_components), coupling_coefficients,
            comm=comm, audit=native_coupling_audit,
        )
        coupling_native_wall = time.perf_counter() - started
        coupling_native_cpu = time.process_time() - cpu_started
        coupling_check = _task41_compare_sparse_functional(
            reference_coupling, native_coupling,
            relative_tolerance=relative_tolerance,
        )
        combination_cutoffs["B_coupling"] = {
            "production": reference_coupling_audit,
            "native": native_coupling_audit,
        }
        timing["B_coupling_production_wall_seconds"] += coupling_reference_wall
        timing["B_coupling_production_process_cpu_seconds"] += coupling_reference_cpu
        timing["B_coupling_native_wall_seconds"] += coupling_native_wall
        timing["B_coupling_native_process_cpu_seconds"] += coupling_native_cpu

        area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
        h_reference = float(area * mode.electric_tangential_norm_sq)
        h_candidate = float(assembly_projection_denominator(mode, cfg, BOUNDARY_PLANE))
        h_error = (
            abs(h_candidate - h_reference) / abs(h_reference)
            if h_reference > 0.0 else float("inf")
        )
        phase_plane_z = float(port_plane_z(mode, cfg))
        gauge_descriptor = phase_gauge_descriptor(mode, cfg, BOUNDARY_PLANE)
        exponent = 1j * complex(mode.k_vector[2]) * phase_plane_z
        global_h_status = "NOT_EVALUATED_UNREPRESENTABLE_GLOBAL_PHASE"
        global_h_error = None
        global_h_reference = None
        if np.isfinite(exponent.real) and -350.0 < exponent.real < 350.0:
            boundary_phase = complex(np.exp(exponent))
            if np.isfinite((boundary_phase.real, boundary_phase.imag)).all() and abs(boundary_phase) > 0.0:
                global_h_reference = float(_mode_projection_denominator(mode, cfg))
                h_from_global = global_h_reference / abs(boundary_phase) ** 2
                global_h_error = abs(h_from_global - h_candidate) / abs(h_candidate)
                global_h_status = "CHECKED"
        global_h_pass = (
            global_h_status != "CHECKED"
            or (global_h_error is not None and global_h_error <= h_relative_tolerance)
        )
        h_pass = bool(
            np.isfinite(h_candidate) and h_candidate > 0.0
            and np.isfinite(h_error) and h_error <= h_relative_tolerance
            and global_h_pass
            and gauge_descriptor["gauge"] == BOUNDARY_PLANE
            and gauge_descriptor["port_plane_z"] == phase_plane_z
            and native_assemblers[(str(mode.side), 0)].boundary_reference_z == phase_plane_z
            and native_assemblers[(str(mode.side), 1)].boundary_reference_z == phase_plane_z
        )
        h_check = {
            "pass": h_pass,
            "phase_gauge_descriptor": gauge_descriptor,
            "boundary_plane_z": phase_plane_z,
            "H_reference_from_area_and_tangential_norm": h_reference,
            "H_candidate_from_boundary_plane_gauge": h_candidate,
            "relative_error_over_reference_H": h_error,
            "global_z_H_equivalence_status": global_h_status,
            "global_z_H_reference": global_h_reference,
            "global_z_H_relative_error_over_boundary_plane_H": global_h_error,
            "relative_tolerance": float(h_relative_tolerance),
            "normalization_scope": "area times tangential electric norm squared; no global-z exponential in native assembly",
        }

        # Match FullspaceDtnAction.apply exactly: D_raw(x)=projection_values dot x,
        # then output_values=coupling_values * D_raw(x)/H. The carrier stores
        # projection_values in its production (already-conjugated) convention.
        candidate_rows = native_rule.candidate_rows
        input_field = np.zeros(len(candidate_rows), dtype=np.complex128)
        reference_d_positions = native_rule.compact_positions(reference_projection[0])
        reference_d_values = np.asarray(reference_projection[1], dtype=np.complex128)
        d_norm = float(np.linalg.norm(reference_d_values))
        if d_norm > 0.0 and h_candidate > 0.0:
            input_field[reference_d_positions] = np.conjugate(reference_d_values) / d_norm
            d_reference_raw = complex(np.dot(
                reference_d_values, input_field[reference_d_positions]
            ))
            candidate_d_positions = native_rule.compact_positions(native_projection[0])
            d_candidate_raw = complex(np.dot(
                native_projection[1], input_field[candidate_d_positions]
            ))
            d_reference_norm = abs(d_reference_raw)
            d_error = (
                abs(d_candidate_raw - d_reference_raw) / d_reference_norm
                if d_reference_norm > 0.0
                else (0.0 if d_candidate_raw == d_reference_raw else float("inf"))
            )
            input_norm = float(np.linalg.norm(input_field))
        else:
            d_reference_raw = d_candidate_raw = 0.0j
            d_reference_norm = input_norm = 0.0
            d_error = float("inf")
        d_raw_check = {
            "pass": bool(input_norm > 0.0 and d_error <= relative_tolerance),
            "input_norm": input_norm,
            "input_sha256": _native_array_sha256(input_field),
            "input_kind": "unit-norm conjugate of the production projection functional on candidate rows",
            "D_raw_x_reference": [d_reference_raw.real, d_reference_raw.imag],
            "D_raw_x_candidate": [d_candidate_raw.real, d_candidate_raw.imag],
            "reference_D_raw_x_magnitude_denominator": d_reference_norm,
            "relative_error_over_reference_D_raw_x": d_error,
            "relative_tolerance": float(relative_tolerance),
            "H_is_applied_after_raw_D": True,
        }
        reference_action = (
            reference_coupling[0],
            np.asarray(reference_coupling[1], dtype=np.complex128) * (d_reference_raw / h_reference),
        )
        candidate_action = (
            native_coupling[0],
            np.asarray(native_coupling[1], dtype=np.complex128) * (d_candidate_raw / h_candidate),
        )
        action_check = _task41_compare_sparse_functional(
            reference_action, candidate_action, relative_tolerance=relative_tolerance
        )
        action_check.update({
            "D_raw_x_reference": [d_reference_raw.real, d_reference_raw.imag],
            "D_raw_x_candidate": [d_candidate_raw.real, d_candidate_raw.imag],
            "H_reference": h_reference,
            "H_candidate": h_candidate,
            "action": "coupling_values * (projection_values dot x / H)",
        })
        b_reference = (
            reference_coupling[0], alpha_test * np.asarray(reference_coupling[1], dtype=np.complex128)
        )
        b_candidate = (
            native_coupling[0], alpha_test * np.asarray(native_coupling[1], dtype=np.complex128)
        )
        b_alpha_check = _task41_compare_sparse_functional(
            b_reference, b_candidate, relative_tolerance=relative_tolerance
        )
        b_alpha_check.update({
            "alpha": [alpha_test.real, alpha_test.imag],
            "H_applied": False,
            "action": "alpha * coupling_values",
        })
        mode_pass = bool(
            all(item["pass"] for item in component_checks)
            and projection_check["pass"] and coupling_check["pass"]
            and h_check["pass"] and d_raw_check["pass"]
            and action_check["pass"] and b_alpha_check["pass"]
        )
        mode_result = {
            "mode_index": int(index),
            "mode_key": [str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)],
            "alpha": [complex(mode.alpha).real, complex(mode.alpha).imag],
            "gamma": [complex(mode.gamma).real, complex(mode.gamma).imag],
            "k_vector": [
                [complex(value).real, complex(value).imag]
                for value in np.asarray(mode.k_vector).reshape(-1)
            ],
            "component_comparisons": component_checks,
            "component_filter_cutoffs": component_cutoffs,
            "combination_filter_cutoffs": combination_cutoffs,
            "D_projection_comparison": projection_check,
            "B_coupling_comparison": coupling_check,
            "B_alpha_action_comparison": b_alpha_check,
            "D_raw_x_action_comparison": d_raw_check,
            "reconstructed_dtn_action_comparison": action_check,
            "H_gauge_comparison": h_check,
            "D_projection_timing": {
                "production_wall_seconds": projection_reference_wall,
                "production_process_cpu_seconds": projection_reference_cpu,
                "native_wall_seconds": projection_native_wall,
                "native_process_cpu_seconds": projection_native_cpu,
            },
            "B_coupling_timing": {
                "production_wall_seconds": coupling_reference_wall,
                "production_process_cpu_seconds": coupling_reference_cpu,
                "native_wall_seconds": coupling_native_wall,
                "native_process_cpu_seconds": coupling_native_cpu,
            },
            "pass": mode_pass,
        }
        comparisons.append(mode_result)
        if progress_callback is not None:
            progress_callback({
                "phase": "task41_b0_native_surface_pair_mode",
                "status": "COMPLETE" if mode_pass else "FAILED",
                "completed": len(comparisons),
                "total": len(selected),
                "mode_result": mode_result,
            })
        if not mode_pass:
            raise ValueError(
                f"Task41 native surface pairing failed an existing reference-norm or H gate: {mode_result['mode_key']}"
            )

    native_rule = next(iter(native_assemblers.values())).rule
    production_stats = {
        f"{side}/{component}": dict(assembler.assembly_stats)
        for (side, component), assembler in production_assemblers.items()
    }
    native_stats = {
        key: value
        for key, value in native_rule.assembly_stats.items()
        if isinstance(value, (int, float, str, bool)) or value is None
    }
    return {
        "status": "PASS_WITH_TASK41_B0_ACTION_GATES",
        "pass": True,
        "mode_count": len(selected),
        "selected_mode_indices": list(selected),
        "scope": "finite representative modes only; same live p6 space, finalized MPC, and actual port geometry",
        "component_reference": "compiled FFCx + dolfinx_mpc vector assembly + full owned-row filter",
        "component_candidate": "FacetPolynomial.integral_native + actual MPC E^H closure + unchanged two-stage cutoff",
        "relative_tolerance_source": "existing Task41 _REGULAR_ACTION_LIMIT (1e-11)",
        "reference_norm_is_the_error_denominator": True,
        "support_symmetric_difference_must_equal_zero": True,
        "H_relative_tolerance_source": "existing boundary-plane normalization gate (1e-14)",
        "B_D_combination_timing_seconds": timing,
        "production_component_assembly_stats": production_stats,
        "native_component_assembly_stats": native_stats,
        "mode_comparisons": comparisons,
    }



def _task41_native_surface_memory_upper_bound(space: Any, mpc: Any, cfg: Any) -> dict[str, Any]:
    """Bound mapping/closure/cache and old/new pairing work from actual axis counts."""

    from petsc4py import PETSc

    axes = tuple(int(value) for value in cfg.mesh_axis_cell_counts)
    if len(axes) != 3 or min(axes) <= 0:
        raise ValueError("Task41 native surface preflight needs valid actual mesh axis counts")
    facets = 2 * axes[0] * axes[1]
    global_rows = int(space.dofmap.index_map.size_global) * int(space.dofmap.index_map_bs)
    index_bytes = np.dtype(PETSc.IntType).itemsize
    scalar_bytes = np.dtype(np.complex128).itemsize
    boundary_rows = facets * 882
    master_count = int(len(mpc.masters.array))
    slave_count = int(len(mpc.slaves))
    candidate_rows = min(global_rows, boundary_rows + master_count)
    mapping_bytes = facets * 2048
    cell_maps_bytes = boundary_rows * 2 * index_bytes
    mpc_closure_bytes = master_count * (index_bytes + scalar_bytes) + slave_count * index_bytes
    candidate_indices_bytes = candidate_rows * 2 * index_bytes
    basis_cache_bytes = boundary_rows * 2 * scalar_bytes
    additional = (
        mapping_bytes + cell_maps_bytes + mpc_closure_bytes
        + candidate_indices_bytes + basis_cache_bytes
    )
    # Include the old full vector plus abs/mask/index extraction temporaries.
    # _vec_nonzero_owned_entries forms float64 magnitudes, int64 nonzero indices,
    # an int64 owned-row range, PETSc indices, and a copied complex value array.
    old_full_vector_bytes = global_rows * scalar_bytes
    old_full_filter_workspace_bytes = global_rows * (
        np.dtype(np.float64).itemsize
        + 2 * np.dtype(np.int64).itemsize
        + index_bytes
        + scalar_bytes
    )
    # The compact vector and component/combined sparse B/D arrays coexist at peak.
    workspace = (
        old_full_vector_bytes + old_full_filter_workspace_bytes
        + candidate_rows * scalar_bytes
        + 6 * candidate_rows * (index_bytes + scalar_bytes)
    )
    return {
        "additional_payload_bytes": int(additional),
        "workspace_bytes": int(workspace),
        "old_full_vector_bytes": int(old_full_vector_bytes),
        "old_full_filter_workspace_bytes": int(old_full_filter_workspace_bytes),
        "boundary_facet_upper_bound": int(facets),
        "boundary_cell_upper_bound": int(facets),
        "boundary_global_row_upper_bound": int(boundary_rows),
        "finalized_mpc_master_count": master_count,
        "finalized_mpc_slave_count": slave_count,
        "candidate_global_row_upper_bound": int(candidate_rows),
        "actual_global_storage_rows": global_rows,
        "resource_classification": "conservative projected upper bound before native inventory/rule/finite-pair allocation",
    }


def _build_split_volume_action(
    mesh_data: Any,
    cfg: Any,
    function_space: Any,
    floquet: Any,
    *,
    jit_options: Mapping[str, Any],
    volume_quadrature_metadata: tuple[Mapping[str, Any], Mapping[str, Any]] | None = None,
) -> Any:
    import ufl

    from .common_3d_forms import _build_physical_volume_terms
    from .fullspace_physical_action import FullspaceSplitVolumeAction

    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    dx = ufl.Measure(
        "dx", domain=mesh_data.mesh, subdomain_data=mesh_data.cell_tags
    )
    curl_curl, material_mass = _build_physical_volume_terms(cfg, u, v, dx)
    if volume_quadrature_metadata is not None:
        curl_curl, material_mass = tuple(
            ufl.Form(tuple(integral.reconstruct(metadata={
                **integral.metadata(), **metadata,
            }) for integral in form.integrals()))
            for form, metadata in zip((curl_curl, material_mass), volume_quadrature_metadata, strict=True)
        )
    return FullspaceSplitVolumeAction(
        curl_curl,
        material_mass,
        function_space,
        mpc=floquet.mpc,
        jit_options=jit_options,
    )


def build_same_mesh_physical_action(
    setup: Mapping[str, Any],
    cfg: Any,
    degree: int,
    *,
    mode_inventory: tuple[Any, Any, Any] | None = None,
    jit_options: Mapping[str, Any] | None = None,
    volume_quadrature_metadata: tuple[Mapping[str, Any], Mapping[str, Any]] | None = None,
    dtn_phase_gauge: str = "global_z",
    verify_dtn_quadrature: bool = False,
    surface_assembly_backend: str = "ffcx",
    pair_native_surface: bool = False,
    native_surface_pair_tolerance: float | None = None,
    surface_functional_checkpoint: Mapping[str, Any] | None = None,
    research_phase_override: tuple[complex, complex] | None = None,
    stage_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Build one physical action from an existing same-mesh level.

    ``setup`` owns the mesh, tags, spaces, and finalized Floquet MPCs.  This
    helper only creates the requested degree's split volume action and
    streaming DtN carrier; the temporary surface assemblers are released as
    soon as the carrier has copied their owner-local functionals.  The
    returned action bundle owns the composite action and must be released with
    :func:`destroy_same_mesh_physical_action`.
    """

    from .common_3d_forms import _validate_physical_split_profile
    from .dtn_boundary_phase_gauge import (
        BOUNDARY_PLANE,
        build_gauge_assembly_context,
        incident_projection_in_solver_coordinates,
        validate_phase_gauge,
    )
    from .dtn_port_3d import _dtn_surface_quadrature_degree
    from .dtn_port_3d import _incident_projection_onto_top_mode
    from .fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from .fullspace_physical_action import FullspacePhysicalAction
    from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS

    if stage_callback is not None and not callable(stage_callback):
        raise TypeError("same-mesh physical action stage callback must be callable")
    if surface_functional_checkpoint is not None and (
        not isinstance(surface_functional_checkpoint, Mapping)
        or set(surface_functional_checkpoint) != {"path", "identity"}
        or not isinstance(surface_functional_checkpoint.get("identity"), Mapping)
    ):
        raise ValueError("surface functional checkpoint must bind one path and execution identity")

    def stage_progress(facts: Mapping[str, Any]) -> None:
        if stage_callback is not None:
            stage_callback(dict(facts))

    def run_stage(phase, operation, *, complete_facts=None):
        if stage_callback is None:
            return operation()
        started = time.perf_counter()
        cpu_started = time.process_time()
        base = {"phase": str(phase)}
        stage_progress({**base, "status": "STARTED"})
        try:
            result = operation()
        except BaseException as error:
            stage_progress({
                **base,
                "status": "FAILED",
                "elapsed_seconds": max(0.0, time.perf_counter() - started),
                "process_cpu_seconds": max(0.0, time.process_time() - cpu_started),
                "error_type": type(error).__name__,
                "error_message": str(error),
            })
            raise
        stage_progress({
            **base,
            "status": "COMPLETE",
            "elapsed_seconds": max(0.0, time.perf_counter() - started),
            "process_cpu_seconds": max(0.0, time.process_time() - cpu_started),
            **dict(complete_facts(result) if complete_facts is not None else {}),
        })
        return result

    degree = int(degree)
    if surface_assembly_backend not in {"ffcx", "native_boundary_plane"}:
        raise ValueError("unsupported same-mesh surface assembly backend")
    if pair_native_surface and surface_assembly_backend != "native_boundary_plane":
        raise ValueError("native surface pairing requires the native boundary-plane backend")
    if pair_native_surface and (
        native_surface_pair_tolerance is None
        or not np.isfinite(float(native_surface_pair_tolerance))
        or float(native_surface_pair_tolerance) <= 0.0
    ):
        raise ValueError("native pairing requires the existing positive Task41 action tolerance")
    if surface_assembly_backend == "native_boundary_plane" and dtn_phase_gauge != BOUNDARY_PLANE:
        raise ValueError("native facet adapter only supports horizontal BOUNDARY_PLANE ports")
    validate_phase_gauge(dtn_phase_gauge)
    _validate_physical_split_profile(cfg)
    try:
        function_space = setup["spaces"][degree]
        floquet = setup["floquets"][degree]
    except KeyError as exc:
        raise ValueError(f"same-mesh setup has no requested degree {degree}") from exc
    if getattr(floquet, "mpc", None) is None:
        raise ValueError("same-mesh physical action requires a finalized Floquet MPC")

    if mode_inventory is None:
        modes, mode_rows, mode_sha = build_dynamic_mode_inventory(cfg)
    else:
        if len(mode_inventory) != 3:
            raise ValueError("mode_inventory must contain modes, rows, and SHA")
        modes, mode_rows, mode_sha = mode_inventory
        modes = tuple(modes)
        mode_rows = tuple(mode_rows)
        mode_sha = str(mode_sha)
    modes = tuple(modes)
    if not modes or len(mode_rows) != len(modes):
        raise ValueError("same-mesh physical mode inventory is incomplete")
    options = SAME_MESH_JIT_OPTIONS if jit_options is None else jit_options
    qdegree = _dtn_surface_quadrature_degree(cfg, list(modes))
    production_assemblers = run_stage(
        "surface_form_jit_all_sides",
        lambda: _surface_assemblers(
            function_space,
            setup["mesh_data"],
            cfg,
            qdegree,
            jit_options=options,
            dtn_phase_gauge=dtn_phase_gauge,
            verify_dtn_quadrature=verify_dtn_quadrature,
            collect_timing=(surface_assembly_backend == "native_boundary_plane"),
            progress_callback=stage_progress if stage_callback is not None else None,
        ),
        complete_facts=lambda value: {"surface_assembler_count": len(value)},
    )
    native_rule = None
    native_rule_stats = None
    surface_pairing = None
    if surface_assembly_backend == "native_boundary_plane":
        if stage_callback is None:
            raise ValueError("Task41 native surface backend requires the supervised allocation-gate callback")
        native_memory_bound = _task41_native_surface_memory_upper_bound(
            function_space, floquet.mpc, cfg
        )
        stage_progress({
            "phase": "task41_b0_native_surface_preflight",
            "status": "STARTED",
            **native_memory_bound,
        })
        stage_progress({
            "phase": "task41_b0_native_surface_preflight",
            "status": "COMPLETE",
            **native_memory_bound,
        })
        compiled_native_identity = _task41_verify_compiled_native_quadrature(
            production_assemblers, qdegree
        )
        from .task40_v22_operator_probe import (
            _V22NativeFacetRule,
            _global_mpc_expansions,
        )
        from .task40_v25_selected_q0 import _q0_reference_surface_inventory
        from .directional_boundary import FacetPolynomial

        (
            mapping_rows,
            _support_groups,
            allowed_local_rows,
            permutation_info,
            surface_inventory,
        ) = _q0_reference_surface_inventory(setup["mesh_data"], function_space, cfg)
        boundary_local_rows = np.unique(np.concatenate(allowed_local_rows)).astype(
            np.int32, copy=False
        )
        boundary_rows = np.asarray(
            function_space.dofmap.index_map.local_to_global(boundary_local_rows),
            dtype=np.int64,
        )
        mapping_facts = {
            **dict(surface_inventory),
            "boundary_global_cell_rows": int(len(boundary_rows)),
            "permutation_sha256": _native_array_sha256(permutation_info),
            "inventory_source": "task40_v25_selected_q0._q0_reference_surface_inventory",
        }
        mpc_expansions = _global_mpc_expansions(
            floquet.mpc, function_space.dofmap.index_map, boundary_rows
        )
        native_rule = _V22NativeFacetRule(
            space=function_space,
            dof_index_map=function_space.dofmap.index_map,
            mapping_rows=mapping_rows,
            permutation_info=permutation_info,
            polynomial=FacetPolynomial(function_space.element.basix_element),
            quadrature_degree=qdegree,
            cfg=cfg,
            mpc_expansions=mpc_expansions,
        )
        assemblers = native_rule.assemblers()
        for key, assembler in assemblers.items():
            assembler.compiled_gauss_identity = production_assemblers[key].compiled_gauss_identity
        del assembler
        if pair_native_surface:
            if stage_callback is not None:
                stage_progress({
                    "phase": "task41_b0_native_surface_pairing",
                    "status": "STARTED",
                    "selected_mode_policy": "per port: smallest transverse phase with an s/p pair plus a distinct largest transverse wavevector",
                    "quadrature_identity": compiled_native_identity,
                    "boundary_mapping": mapping_facts,
                    "candidate_global_row_count": int(len(native_rule.candidate_rows)),
                    "mpc_expansion_slave_count": int(len(mpc_expansions)),
                    "mpc_master_row_count": int(len(native_rule._master_rows)),
                })
            try:
                surface_pairing = _task41_pair_native_surface_assemblers(
                    modes,
                    production_assemblers,
                    assemblers,
                    floquet.mpc,
                    cfg,
                    relative_tolerance=float(native_surface_pair_tolerance),
                    progress_callback=stage_progress if stage_callback is not None else None,
                )
            except BaseException as error:
                if stage_callback is not None:
                    stage_progress({
                        "phase": "task41_b0_native_surface_pairing",
                        "status": "FAILED",
                        "error_type": type(error).__name__,
                        "error_message": str(error),
                    })
                raise
            surface_pairing["compiled_native_quadrature"] = compiled_native_identity
            surface_pairing["boundary_mapping"] = mapping_facts
            surface_pairing["compact_candidate_row_count"] = int(len(native_rule.candidate_rows))
            surface_pairing["compact_candidate_rows_sha256"] = _native_array_sha256(
                native_rule.candidate_rows
            )
            surface_pairing["mpc_expansion_slave_count"] = int(len(mpc_expansions))
            surface_pairing["mpc_master_row_count"] = int(len(native_rule._master_rows))
            if stage_callback is not None:
                stage_progress({
                    **surface_pairing,
                    "phase": "task41_b0_native_surface_pairing",
                    "qualification_status": surface_pairing["status"],
                    "status": "COMPLETE" if surface_pairing["pass"] else "FAILED",
                })
            if not surface_pairing["pass"]:
                raise ValueError("Task41 native boundary pairing differs from compiled production functionals")
        # The native adapters keep the verified compiled identity for context binding;
        # the production PETSc forms are no longer needed after the finite pairing.
        del production_assemblers
    else:
        assemblers = production_assemblers
        del production_assemblers
    carrier = None
    dtn_action = None
    volume_action = None
    physical_action = None
    assembly_context = None
    compiled_gauss = None
    try:
        if dtn_phase_gauge == BOUNDARY_PLANE:
            assembly_context = run_stage(
                "boundary_plane_gauge_context",
                lambda: build_gauge_assembly_context(
                    function_space, setup["mesh_data"], floquet.mpc, cfg, qdegree, assemblers,
                    phase_override=research_phase_override,
                ),
            )
            if surface_assembly_backend == "native_boundary_plane":
                source_identity = dict(assembly_context["source_sha256"])
                native_source = Path(__file__).with_name("task40_v22_operator_probe.py")
                import hashlib
                source_identity["task40_v22_operator_probe.py"] = hashlib.sha256(
                    native_source.read_bytes()
                ).hexdigest()
                inventory_source = Path(__file__).with_name("task40_v25_selected_q0.py")
                source_identity["task40_v25_selected_q0.py"] = hashlib.sha256(
                    inventory_source.read_bytes()
                ).hexdigest()
                kernel_source = Path(__file__).with_name("directional_boundary.py")
                source_identity["directional_boundary.py"] = hashlib.sha256(
                    kernel_source.read_bytes()
                ).hexdigest()
                updated_context = dict(assembly_context)
                updated_context["source_sha256"] = source_identity
                gauss = dict(updated_context["gauss"])
                gauss["assembly_backend"] = "FacetPolynomial.integral_native on horizontal BOUNDARY_PLANE facets"
                gauss["native_quadrature_identity"] = dict(compiled_native_identity)
                updated_context["gauss"] = gauss
                from .dtn_boundary_phase_gauge import deep_frozen_identity
                assembly_context = deep_frozen_identity(updated_context)
        carrier = run_stage(
            "dtn_carrier_build",
            lambda: build_fullspace_dtn_carrier_from_surface(
                modes, assemblers, floquet.mpc, cfg,
                phase_gauge=dtn_phase_gauge,
                assembly_context=assembly_context,
                persistence_path=(
                    surface_functional_checkpoint["path"]
                    if surface_functional_checkpoint is not None else None
                ),
                persistence_identity=(
                    surface_functional_checkpoint["identity"]
                    if surface_functional_checkpoint is not None else None
                ),
                progress_callback=stage_progress if stage_callback is not None else None,
            ),
            complete_facts=lambda value: {
                "carrier_mode_count": len(value.entries),
                **({"surface_functional_checkpoint": dict(value.persistence_facts)}
                   if getattr(value, "persistence_facts", None) is not None else {}),
                **({"native_surface_assembly_stats": dict(native_rule.assembly_stats)}
                   if native_rule is not None else {}),
                **({"representative_surface_pairing": surface_pairing}
                   if surface_pairing is not None else {}),
            },
        )
    finally:
        # The carrier owns copied sparse functionals; assemblers own only the
        # temporary compiled surface forms and their phase constants.
        if verify_dtn_quadrature or dtn_phase_gauge == BOUNDARY_PLANE:
            compiled_gauss = {
                f"{side}/{component}": assembler.compiled_gauss_identity
                for (side, component), assembler in assemblers.items()
            }
        del assemblers
    if native_rule is not None:
        native_rule_stats = dict(native_rule.assembly_stats)
        del native_rule
        del mapping_rows, _support_groups, allowed_local_rows, permutation_info
        del surface_inventory, boundary_local_rows, boundary_rows, mapping_facts
        del mpc_expansions, compiled_native_identity
    try:
        dtn_action = run_stage(
            "dtn_action_wrap",
            lambda: build_fullspace_dtn_action(carrier, comm=setup["mesh"].comm),
        )
        volume_action = run_stage(
            "volume_form_jit",
            lambda: _build_split_volume_action(
                setup["mesh_data"],
                cfg,
                function_space,
                floquet,
                jit_options=options,
                volume_quadrature_metadata=volume_quadrature_metadata,
            ),
        )
        physical_action = run_stage(
            "physical_action_combine",
            lambda: FullspacePhysicalAction(volume_action, dtn_action),
        )
        owned_volume_action = volume_action
        owned_dtn_action = dtn_action
        dtn_action = None
        volume_action = None
        incident_projections = run_stage(
            "incident_projection_inventory",
            lambda: tuple(
                incident_projection_in_solver_coordinates(mode, cfg, dtn_phase_gauge)
                if dtn_phase_gauge == BOUNDARY_PLANE else _incident_projection_onto_top_mode(mode, cfg)
                for mode in modes
            ),
            complete_facts=lambda value: {"completed": len(value), "total": len(modes)},
        )
        return {
            "dtn_phase_gauge": dtn_phase_gauge,
            "surface_assembly_backend": surface_assembly_backend,
            **({"representative_surface_pairing": surface_pairing}
               if surface_pairing is not None else {}),
            **({
                "physical_generator_manifest_sha256": mode_sha,
                "assembly_mode_manifest_sha256": carrier.mode_manifest_sha256,
                "assembly_context_sha256": carrier.assembly_context_sha256,
                "compiled_surface_gauss_identity": compiled_gauss,
                "solver_auxiliary_coordinate": "boundary_plane",
                "global_output_conversion": "explicit-representability-gated",
            } if dtn_phase_gauge == BOUNDARY_PLANE else {}),
            "schema": "task038.same_mesh_hcurl_pmg.physical-action.v1",
            "setup": setup,
            "cfg": cfg,
            "degree": degree,
            "action": physical_action,
            "physical_action": physical_action,
            "volume_action": owned_volume_action,
            "dtn_action": owned_dtn_action,
            "modes": modes,
            "mode_rows": mode_rows,
            "mode_sha256": mode_sha,
            "dtn_quadrature_degree": int(qdegree),
            "volume_quadrature_metadata": volume_quadrature_metadata,
            "incident_projections": incident_projections,
            "research_phase_override": (
                None if research_phase_override is None
                else tuple(map(complex, research_phase_override))
            ),
        }
    except Exception:
        if physical_action is not None:
            physical_action.destroy()
        else:
            if dtn_action is not None:
                dtn_action.destroy()
            if volume_action is not None:
                volume_action.destroy()
        raise


def destroy_same_mesh_physical_action(bundle: dict[str, Any]) -> None:
    """Destroy one action bundle without touching its borrowed setup."""

    if not bundle:
        return
    action = bundle.pop("action", None)
    if action is not None:
        action.destroy()
    bundle.clear()


def build_p6_same_mesh_physical_bundle(
    cfg: Any,
    comm: Any,
    *,
    stage_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Attach the exact p6 volume+DtN operator to the selected positive setup."""

    from .fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from .fullspace_physical_action import FullspacePhysicalAction
    from .fullspace_same_mesh_hcurl_pmg_setup import (
        SAME_MESH_JIT_OPTIONS,
        build_p6_same_mesh_setup,
    )
    from .common_3d_forms import _validate_physical_split_profile
    from .dtn_port_3d import _dtn_surface_quadrature_degree
    from .dtn_port_3d import _incident_projection_onto_top_mode

    if int(comm.size) != 1:
        raise ValueError("the P0 physical lane is fixed to MPI1")
    _validate_physical_split_profile(cfg)
    _notify_stage(stage_callback, "positive_setup_started", {"levels": [6, 3, 1]})
    setup = build_p6_same_mesh_setup(cfg, comm)
    dtn_action = None
    volume_action = None
    physical_action = None
    try:
        _notify_stage(
            stage_callback,
            "positive_setup_complete",
            {"levels": [6, 3, 1], "profile": PHYSICAL_PROFILE},
        )
        _notify_stage(stage_callback, "mode_inventory_started", {})
        modes, mode_rows, mode_sha = build_dynamic_mode_inventory(cfg)
        qdegree = _dtn_surface_quadrature_degree(cfg, list(modes))
        _notify_stage(
            stage_callback,
            "mode_inventory_complete",
            {
                "mode_count": int(len(modes)),
                "mode_manifest_sha256": str(mode_sha),
                "dtn_quadrature_degree": int(qdegree),
            },
        )
        p6_space = setup["spaces"][6]
        p6_floquet = setup["floquets"][6]
        _notify_stage(stage_callback, "surface_assemblers_started", {"count": 4})
        assemblers = _surface_assemblers(
            p6_space,
            setup["mesh_data"],
            cfg,
            qdegree,
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        _notify_stage(
            stage_callback,
            "surface_assemblers_complete",
            {"count": int(len(assemblers))},
        )
        _notify_stage(
            stage_callback,
            "dtn_carrier_started",
            {"mode_count": int(len(modes))},
        )
        carrier = build_fullspace_dtn_carrier_from_surface(
            modes, assemblers, p6_floquet.mpc, cfg
        )
        _notify_stage(
            stage_callback,
            "dtn_carrier_complete",
            {"mode_count": int(len(modes)), "surface_assembler_count": int(len(assemblers))},
        )
        dtn_action = build_fullspace_dtn_action(carrier, comm=comm)
        _notify_stage(
            stage_callback,
            "dtn_action_complete",
            {"mode_count": int(len(modes))},
        )
        del carrier, assemblers

        _notify_stage(
            stage_callback,
            "physical_volume_action_started",
            {
                "form": "exact_maxwell_volume_split",
                "component_count": 2,
                "components": ["curl_curl", "complex_material_mass"],
            },
        )
        volume_action = _build_split_volume_action(
            setup["mesh_data"],
            cfg,
            p6_space,
            p6_floquet,
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        _notify_stage(
            stage_callback,
            "physical_volume_action_complete",
            {
                "form": "exact_maxwell_volume_split",
                "component_count": 2,
                "components": ["curl_curl", "complex_material_mass"],
                "volume_action": True,
            },
        )
        physical_action = FullspacePhysicalAction(volume_action, dtn_action)
        owned_volume_action = volume_action
        owned_dtn_action = dtn_action
        volume_action = None
        dtn_action = None
        incident_projections = tuple(
            _incident_projection_onto_top_mode(mode, cfg) for mode in modes
        )
        bundle = {
            "schema": PHYSICAL_BUNDLE_SCHEMA,
            "profile": PHYSICAL_PROFILE,
            "degree": 6,
            "setup": setup,
            "cfg": cfg,
            "physical_action": physical_action,
            "dtn_action": owned_dtn_action,
            "volume_action": owned_volume_action,
            "modes": tuple(modes),
            "mode_rows": tuple(mode_rows),
            "mode_sha256": str(mode_sha),
            "incident_projections": incident_projections,
            "dtn_quadrature_degree": int(qdegree),
        }
        _notify_stage(
            stage_callback,
            "bundle_built",
            {
                "levels": [6, 3, 1],
                "mode_count": int(len(modes)),
                "physical_action": True,
                "volume_component_count": 2,
                "volume_components": ["curl_curl", "complex_material_mass"],
            },
        )
        return bundle
    except Exception:
        if physical_action is not None:
            physical_action.destroy()
        else:
            if dtn_action is not None:
                dtn_action.destroy()
            if volume_action is not None:
                volume_action.destroy()
        from .fullspace_same_mesh_hcurl_pmg_setup import (
            destroy_p6_same_mesh_setup_bundle,
        )

        destroy_p6_same_mesh_setup_bundle(setup)
        raise


def audit_p6_same_mesh_physical_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Return setup and physical action facts without creating a source/KSP."""

    from .fullspace_same_mesh_hcurl_pmg_setup import audit_p6_same_mesh_setup

    setup_audit = audit_p6_same_mesh_setup(bundle["setup"])
    physical_audit = dict(bundle["physical_action"].audit)
    physical_audit.update(
        {
            "mode_manifest_sha256": str(bundle["mode_sha256"]),
            "mode_count": int(len(bundle["modes"])),
            "dtn_quadrature_degree": int(bundle["dtn_quadrature_degree"]),
            "physical_form": (
                "exact_maxwell_split_volume_plus_unchanged_streaming_fourier_dtn"
            ),
            "volume_component_count": 2,
            "volume_components": ["curl_curl", "complex_material_mass"],
        }
    )
    return {
        "schema": PHYSICAL_BUNDLE_SCHEMA,
        "profile": PHYSICAL_PROFILE,
        "setup_audit": setup_audit,
        "physical_action": physical_audit,
        "architecture": {
            "levels": [6, 3, 1],
            "same_physical_mesh": True,
            "p6_matrix_free": True,
            "p6_global_aij": False,
            "high_order_global_aij": False,
            "p3_sparse_allowed": True,
            "p1_sparse_allowed": True,
            "global_dense_transfer": False,
            "global_transfer_matrix": False,
            "numeric_allgather": False,
            "p6_factor": False,
            "outer_ksp_created": True,
            "physical_solve": True,
            "dtn": True,
            "recovery": True,
            "source_is_pde_rhs": True,
        },
    }


def build_physical_rhs(bundle: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    """Build the current dtn-port physical RHS, without applying the operator."""

    from .dtn_port_3d import _assemble_mpc_vector, _incident_top_traction_form
    from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS

    setup = bundle["setup"]
    cfg = bundle["cfg"]
    degree = int(bundle["degree"])
    space = setup["spaces"][degree]
    floquet = setup["floquets"][degree]
    base = _assemble_mpc_vector(
        _incident_top_traction_form(space, setup["mesh_data"], cfg),
        floquet.mpc,
        quadrature_degree=int(bundle["dtn_quadrature_degree"]),
        jit_options=SAME_MESH_JIT_OPTIONS,
    )
    rhs = base.duplicate()
    try:
        bundle["physical_action"].compose_physical_rhs(
            base,
            bundle["incident_projections"],
            rhs,
        )
    finally:
        base.destroy()
    return rhs, {
        "generation": "dtn_port_modal_physical_rhs",
        "role": "physical_maxwell_rhs",
        "degree": degree,
        "phase_application": "finalized_floquet_mpc_once",
        "mode_count": int(len(bundle["modes"])),
        "mode_manifest_sha256": str(bundle["mode_sha256"]),
    }


def recover_p0_outputs(
    bundle: Mapping[str, Any], solution: Any, output_dir: Path, *,
    canonical_export: Any | None = None,
    export_all_port_modes: bool = False,
    jit_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recover E/H and compute the existing modal and diagnostic outputs."""

    from dolfinx import fem
    from ..postprocessing.diffraction_3d import compute_diffraction_orders_3d
    from ..postprocessing.postprocess_3d import save_airbox_3d_fields
    from ..postprocessing.rta_3d import compute_volume_absorption_3d
    from .dtn_port_3d import _port_power_metrics
    from .dtn_boundary_phase_gauge import GLOBAL_Z, validate_phase_gauge
    from ..common.modes_3d import incident_power_3d

    setup = bundle["setup"]
    floquet = setup["floquets"][6]
    field = fem.Function(floquet.mpc.function_space, name="E_total")
    try:
        solution.copy(field.x.petsc_vec)
        field.x.scatter_forward()
        floquet.mpc.homogenize(field)
        field.x.scatter_forward()
        floquet.mpc.backsubstitution(field)
        field.x.scatter_forward()
        recovered_auxiliary = bundle["dtn_action"].recover_auxiliary(solution)
        aux = np.asarray(recovered_auxiliary, dtype=np.complex128)
        del recovered_auxiliary
        dtn_phase_gauge = validate_phase_gauge(bundle.get("dtn_phase_gauge", GLOBAL_Z))
        port_metrics = _port_power_metrics(
            bundle["cfg"],
            list(bundle["modes"]),
            aux,
            list(bundle["incident_projections"]),
            dtn_phase_gauge=dtn_phase_gauge,
        )
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        canonical_facts = None if canonical_export is None else canonical_export(field, output_dir)
        if export_all_port_modes:
            from .dtn_port_3d import _write_port_outputs

            _write_port_outputs(output_dir, bundle['cfg'], list(bundle['modes']), aux,
                list(bundle['incident_projections']), port_metrics, setup['mesh_data'].mesh.comm,
                dtn_phase_gauge=dtn_phase_gauge)
        field_export = save_airbox_3d_fields(
            setup["mesh_data"], bundle["cfg"], field, output_dir,
            jit_options=jit_options,
        )
        volume_metrics = compute_volume_absorption_3d(
            setup["mesh_data"],
            bundle["cfg"],
            field,
            output_dir,
            incident_power=incident_power_3d(bundle["cfg"]),
            port_metrics=port_metrics,
            jit_options=jit_options,
        )
        diffraction_metrics = compute_diffraction_orders_3d(
            setup["mesh_data"], bundle["cfg"], field, output_dir,
            jit_options=jit_options,
        )
        facts = {
            "field_model": "total_field",
            "electric_finite": bool(np.all(np.isfinite(field.x.array))),
            "auxiliary_finite": bool(np.all(np.isfinite(aux))),
            "auxiliary": aux,
            "dtn_phase_gauge": dtn_phase_gauge,
            "port_metrics": port_metrics,
            "volume_metrics": volume_metrics,
            "diffraction_metrics": diffraction_metrics,
            "diffraction_channel_count": int(
                diffraction_metrics["diffraction_channel_count"]
            ),
            "field_export": field_export,
        }
        if canonical_export is not None:
            facts['canonical_vector'] = canonical_facts
        return facts
    finally:
        del field


def release_p6_same_mesh_solver_stack(bundle: dict[str, Any]) -> None:
    """Release only the auxiliary hierarchy, preserving physical recovery state."""

    setup = bundle["setup"]
    upper = setup.pop("upper_cycle", None)
    if upper is not None:
        upper.destroy()
    for name in (
        "lower_cycle",
        "p63_owner_transfer",
        "p31_owner_transfer",
        "p6_shell",
        "p63_local_transfer",
        "p31_local_transfer",
    ):
        setup.pop(name, None)
    coarse_solver = setup.pop("owned_coarse_solver", None)
    if coarse_solver is not None:
        coarse_solver.destroy()
    for name in ("p3_matrix", "p1_matrix"):
        matrix = setup.pop(name, None)
        if matrix is not None:
            matrix.destroy()


def destroy_p6_same_mesh_physical_bundle(bundle: dict[str, Any]) -> None:
    """Destroy physical action first, then the selected setup bundle once."""

    if not bundle:
        return
    physical = bundle.pop("physical_action", None)
    setup = bundle.pop("setup", None)
    if physical is not None:
        physical.destroy()
    if setup:
        from .fullspace_same_mesh_hcurl_pmg_setup import (
            destroy_p6_same_mesh_setup_bundle,
        )

        destroy_p6_same_mesh_setup_bundle(setup)
    bundle.clear()


__all__ = (
    "PHYSICAL_BUNDLE_SCHEMA",
    "PHYSICAL_PROFILE",
    "audit_p6_same_mesh_physical_bundle",
    "build_same_mesh_physical_action",
    "build_p6_same_mesh_physical_bundle",
    "build_physical_rhs",
    "destroy_p6_same_mesh_physical_bundle",
    "destroy_same_mesh_physical_action",
    "release_p6_same_mesh_solver_stack",
    "recover_p0_outputs",
)
