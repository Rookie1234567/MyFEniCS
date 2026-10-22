"""Task43 same-mesh h100 p3 anchor runner.

Run one case per process.  The native case uses the ordinary degree-three
Nedelec space and ``standard_full`` backend; the empty-h cases use the
qualified p6 carrier with a geometry-bound all-p3 active-space plan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task43_hp_adaptivity.profile import task43_initial_profile
from src.adaptivity.stage4_local_h import (
    build_stage4_local_h_mesh_data,
    stage4_local_h_refinement_plan_payload,
)
from src.adaptivity.variable_p_degree_plan import cell_box_catalog
from src.common.config_3d import (
    ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
    STANDARD_FULL_ASSEMBLY_BACKEND,
    resolve_stage4_full3d_assembly_backend,
)
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.postprocessing.physical_field_comparison import (
    build_common_volume_quadrature,
    magnetic_field_from_electric_curl,
    scattered_field_samples,
    weighted_vector_field_metrics,
)
from src.postprocessing.physical_field_sampling import (
    prepare_cell_local_vector_field_export,
    sample_cell_local_vector_fields,
)
from src.solvers.dtn_port_3d import compute_stage4_independent_active_action
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)

_CASES = {
    "native_p3_mpi1": (1, "native_p3"),
    "empty_h_active_p3_mpi1": (1, "empty_h_active_p3"),
    "empty_h_active_p3_mpi2": (2, "empty_h_active_p3"),
}
_THREAD_ENV = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
_SOURCE_FILES = (
    "benchmarks/task43_hp_adaptivity/h100_anchor.py",
    "benchmarks/task43_hp_adaptivity/profile.py",
    "src/adaptivity/exact_sequence_variable_p.py",
    "src/adaptivity/hcurl_broken_cell_trace.py",
    "src/adaptivity/hcurl_broken_trace_graph.py",
    "src/adaptivity/stage4_local_h.py",
    "src/adaptivity/variable_p_degree_plan.py",
    "src/adaptivity/variable_p_entity_map.py",
    "src/common/analytic_fields_3d.py",
    "src/common/config_3d.py",
    "src/common/modes_3d.py",
    "src/constraints/floquet_3d.py",
    "src/geometry/mesh_builder_3d.py",
    "src/geometry/task43_hp_adaptivity_axis_plan.py",
    "src/postprocessing/diffraction_3d.py",
    "src/postprocessing/physical_field_comparison.py",
    "src/postprocessing/physical_field_sampling.py",
    "src/postprocessing/flat_layer_reference_3d.py",
    "src/postprocessing/postprocess_3d.py",
    "src/postprocessing/rta_3d.py",
    "src/solvers/common_3d_fields.py",
    "src/solvers/common_3d_postprocess.py",
    "src/solvers/common_3d_solve.py",
    "src/solvers/common_3d_forms.py",
    "src/solvers/common_3d_utils.py",
    "src/solvers/common_3d_case_flow.py",
    "src/solvers/dtn_port_3d.py",
    "src/solvers/hcurl_blocked_gram_tensor.py",
    "src/solvers/hcurl_variable_p_local.py",
    "src/solvers/hcurl_variable_p_assembly.py",
    "src/solvers/hcurl_variable_p_reduction.py",
    "src/solvers/independent_active_action.py",
    "src/solvers/solve_maxwell_3d_stage_4b_block_grating.py",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _log_stage(
    comm: MPI.Intracomm,
    started: float,
    stage: str,
    status: str,
    **details: Any,
) -> None:
    if comm.rank == 0:
        print(
            json.dumps(
                {
                    "task43_stage": stage,
                    "status": status,
                    "elapsed_wall_seconds": time.perf_counter() - started,
                    **details,
                },
                sort_keys=True,
                default=_json_default,
            ),
            flush=True,
        )


def _validate_reference_run(
    run_root: Path,
    *,
    expected_case_id: str,
) -> dict[str, Any]:
    record_path = run_root / "task43_h100_anchor_record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("case_id") != expected_case_id:
        raise ValueError(
            f"reference case identity mismatch: expected {expected_case_id}, "
            f"got {record.get('case_id')}"
        )
    if record.get("gates", {}).get("pass") is not True:
        raise ValueError("reference anchor did not pass all of its gates")
    if record.get("solver", {}).get("official_result") is not True:
        raise ValueError("reference solver result is not official")
    if record.get("solver", {}).get("case_status") != "completed":
        raise ValueError("reference solver case is not completed")

    expected_files = (
        (
            run_root / "field_samples_q8_q10.npz",
            record.get("field_samples", {}).get("file"),
            record.get("field_samples", {}).get("sha256"),
            "field samples",
        ),
        (
            run_root / "solve" / "dtn_port_diffraction_orders_3d.json",
            record.get("power", {}).get("channel_rows_file"),
            record.get("power", {}).get("channel_rows_sha256"),
            "ordered channel rows",
        ),
    )
    verified: dict[str, str] = {}
    for expected_path, recorded_path, recorded_hash, label in expected_files:
        if not isinstance(recorded_path, str) or not isinstance(recorded_hash, str):
            raise TypeError(f"reference record lacks {label} identity")
        actual_path = Path(recorded_path).resolve()
        if actual_path != expected_path.resolve():
            raise ValueError(f"reference {label} path differs from its record")
        actual_hash = _sha256_file(actual_path)
        if actual_hash != recorded_hash:
            raise ValueError(f"reference {label} hash differs from its record")
        verified[label.replace(" ", "_")] = actual_hash
    return {
        "case_id": expected_case_id,
        "record_sha256": _sha256_file(record_path),
        "verified_artifact_sha256": verified,
    }


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _h100_config(*, kind: str, case_name: str):
    degree = 3 if kind == "native_p3" else 6
    cfg = task43_initial_profile(case_name=case_name)
    cfg.nedelec_degree = degree
    cfg.visualization_degree = degree
    # This run deliberately resolves its own h=100 nm mesh.  In particular,
    # it does not retain the frozen 3x10x6 starting-axis profile.
    cfg.mesh_plan_id = None
    cfg.mesh_plan_sha256 = None
    cfg.mesh_axis_cell_counts = None
    cfg.mesh_axis_x_values = None
    cfg.mesh_axis_y_values = None
    cfg.mesh_axis_z_values = None
    cfg.mesh_axis_z_profile = None
    cfg.mesh_spacing_mode = "boundary_fitted"
    cfg.mesh_target_size = 100.0
    cfg.mesh_cell_type = "hexahedron"
    cfg.mesh_refined_size = None
    cfg.mesh_refinement_radius = None
    cfg.stage4_variable_p_cell_degree_plan = None
    cfg.stage4_local_h_refinement_plan = None
    cfg.matrix_diagnostics_assemble_only = False
    cfg.matrix_diagnostics_factorization_only = False
    cfg.unique_output = False
    cfg.stage4_full3d_assembly_backend = (
        STANDARD_FULL_ASSEMBLY_BACKEND
        if kind == "native_p3"
        else ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
    )
    if kind == "native_p3":
        cfg.stage4_variable_p_raw_tensor_backend = None
    return cfg


def _mesh_axes(mesh, comm: MPI.Intracomm) -> tuple[np.ndarray, ...]:
    topological_dimension = int(mesh.topology.dim)
    cell_map = mesh.topology.index_map(topological_dimension)
    local_vertices = [
        np.asarray(
            mesh.geometry.x[np.asarray(mesh.geometry.dofmap[cell]), :3],
            dtype=np.float64,
        )
        for cell in range(int(cell_map.size_local))
    ]
    if local_vertices:
        local_points = np.vstack(local_vertices)
    else:
        local_points = np.zeros((0, 3), dtype=np.float64)
    packets = comm.allgather(local_points)
    all_points = np.vstack([packet for packet in packets if len(packet)])
    axes = tuple(np.unique(all_points[:, axis]) for axis in range(3))
    return axes


def _assert_h100_mesh(mesh_data, axes: tuple[np.ndarray, ...]) -> dict[str, Any]:
    cell_map = mesh_data.mesh.topology.index_map(mesh_data.mesh.topology.dim)
    global_cells = int(cell_map.size_global)
    cell_counts = tuple(len(axis) - 1 for axis in axes)
    if global_cells != 36 or cell_counts != (3, 3, 4):
        raise RuntimeError(
            "h100 anchor mesh differs from the qualified 36-cell 3x3x4 mesh: "
            f"cells={global_cells}, axes={cell_counts}"
        )
    if tuple(mesh_data.mesh_cells_resolved) != cell_counts:
        raise RuntimeError(
            "mesh builder cell counts disagree with resolved coordinate axes: "
            f"builder={mesh_data.mesh_cells_resolved}, axes={cell_counts}"
        )
    expected_bounds = ((0.0, 50.0), (0.0, 50.0), (-10.0, 130.0))
    for axis, bounds in zip(axes, expected_bounds, strict=True):
        if not np.isclose(axis[0], bounds[0]) or not np.isclose(axis[-1], bounds[1]):
            raise RuntimeError(f"resolved mesh has unexpected domain endpoints: {axis}")
    return {
        "global_cells": global_cells,
        "axis_cell_counts_xyz": list(cell_counts),
        "axes_nm": [axis.tolist() for axis in axes],
        "axis_values_sha256": _sha256_json([axis.tolist() for axis in axes]),
        "spacing_mode_resolved": str(mesh_data.mesh_spacing_mode_resolved),
        "mesh_cell_type_resolved": str(mesh_data.mesh_cell_type_resolved),
        "material_plane_alignment": mesh_data.material_plane_alignment,
    }


def _native_explicit_residual(linear_system: dict[str, Any]) -> dict[str, float]:
    matrix = linear_system["A"]
    rhs = linear_system["b"]
    solution = linear_system["x"]
    if matrix is None or rhs is None or solution is None:
        raise RuntimeError("native standard solver did not retain A, b, and x")
    residual = rhs.duplicate()
    try:
        matrix.mult(solution, residual)
        residual.axpy(PETSc.ScalarType(-1.0), rhs)
        residual_norm = float(residual.norm())
        rhs_norm = float(rhs.norm())
        return {
            "explicit_augmented_Ax_minus_b_norm": residual_norm,
            "augmented_rhs_norm": rhs_norm,
            "relative_to_rhs": residual_norm / max(rhs_norm, 1.0e-30),
            "classification": "standard_full_explicit_augmented_true_residual",
        }
    finally:
        residual.destroy()


def _field_capture(
    field,
    mesh_data,
    cfg,
    comm: MPI.Intracomm,
    reference_axes: tuple[np.ndarray, ...] | None,
) -> dict[str, Any]:
    export = prepare_cell_local_vector_field_export(field)
    axes = _mesh_axes(mesh_data.mesh, comm)
    mesh_identity = _assert_h100_mesh(mesh_data, axes)
    if reference_axes is not None and any(
        not np.array_equal(axis, reference_axis)
        for axis, reference_axis in zip(axes, reference_axes, strict=True)
    ):
        raise RuntimeError("candidate mesh axes differ from the native h100 mesh")
    samples: dict[str, dict[str, np.ndarray]] = {}
    sample_error = None
    for order in (8, 10):
        common_axes = [axes] if reference_axes is None else [reference_axes, axes]
        quadrature = build_common_volume_quadrature(
            common_axes, gauss_order=order
        )
        sampled = sample_cell_local_vector_fields(
            {
                "E_total": export.electric_dgq6,
                "curl_E_total": export.curl_electric_dgq6,
            },
            quadrature.points_nm,
        )
        if comm.rank == 0:
            try:
                assert sampled is not None
                curl = sampled["curl_E_total"]
                magnetic = magnetic_field_from_electric_curl(
                    curl,
                    magnetic_field_scale_A_per_m=cfg.magnetic_field_scale_A_per_m,
                    k0_per_nm=cfg.k0,
                    mu_r=cfg.mu_r,
                )
                samples[f"q{order}"] = {
                    "points_nm": quadrature.points_nm,
                    "weights_nm3": quadrature.weights_nm3,
                    "E_total": sampled["E_total"],
                    "curl_E_total": curl,
                    "H_total_A_per_m": magnetic,
                }
            except (
                AssertionError,
                IndexError,
                OverflowError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as exc:
                sample_error = f"{type(exc).__name__}: {exc}"
        errors = comm.allgather(sample_error)
        if any(error is not None for error in errors):
            raise RuntimeError(
                "field sample postprocessing failed collectively: "
                + "; ".join(
                    f"rank {rank}: {error}"
                    for rank, error in enumerate(errors)
                    if error is not None
                )
            )
    return {
        "source_degree": int(export.source_degree),
        "target_degree": int(export.target_degree),
        "representation": export.representation,
        "mesh_identity": mesh_identity,
        "samples": samples,
    }


def _array_norm(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sqrt(np.dot(weights, np.sum(np.abs(values) ** 2, axis=1))))


def _field_comparison(
    current: dict[str, dict[str, np.ndarray]],
    reference_path: Path,
    cfg,
) -> dict[str, Any]:
    from src.common.analytic_fields_3d import (
        electric_field_code_values,
        magnetic_field_code_values,
    )

    volume = float(cfg.period_x * cfg.period_y * (cfg.domain_z_max - cfg.domain_z_min))
    e_floor = float(np.sqrt(volume))
    h_floor = e_floor * float(cfg.magnetic_field_scale_A_per_m)
    g_floor = float(np.sqrt(2.0 * volume))
    result: dict[str, Any] = {}
    with np.load(reference_path, allow_pickle=False) as reference:
        for order in (8, 10):
            key = f"q{order}"
            observed = current[key]
            ref_points = reference[f"{key}_points_nm"]
            if not np.array_equal(observed["points_nm"], ref_points):
                raise ValueError(f"{key} quadrature points differ from native p3")
            weights = reference[f"{key}_weights_nm3"]
            if not np.array_equal(observed["weights_nm3"], weights):
                raise ValueError(f"{key} quadrature weights differ from native p3")
            background_e = electric_field_code_values(cfg, observed["points_nm"])
            background_h = cfg.magnetic_field_scale_A_per_m * magnetic_field_code_values(
                cfg, observed["points_nm"]
            )
            reference_e_scattered = scattered_field_samples(
                reference[f"{key}_E_total"], background_e
            )
            current_e_scattered = scattered_field_samples(
                observed["E_total"], background_e
            )
            reference_h_scattered = scattered_field_samples(
                reference[f"{key}_H_total_A_per_m"], background_h
            )
            current_h_scattered = scattered_field_samples(
                observed["H_total_A_per_m"], background_h
            )

            metrics = {
                "E_total_code": weighted_vector_field_metrics(
                    reference[f"{key}_E_total"],
                    observed["E_total"],
                    weights,
                    reference_norm_floor=e_floor,
                ),
                "curl_E_over_k0_code": weighted_vector_field_metrics(
                    reference[f"{key}_curl_E_total"] / cfg.k0,
                    observed["curl_E_total"] / cfg.k0,
                    weights,
                    reference_norm_floor=e_floor,
                ),
                "H_total_A_per_m": weighted_vector_field_metrics(
                    reference[f"{key}_H_total_A_per_m"],
                    observed["H_total_A_per_m"],
                    weights,
                    reference_norm_floor=h_floor,
                ),
                "E_scattered_code": weighted_vector_field_metrics(
                    reference_e_scattered,
                    current_e_scattered,
                    weights,
                    reference_norm_floor=e_floor,
                ),
                "H_scattered_A_per_m": weighted_vector_field_metrics(
                    reference_h_scattered,
                    current_h_scattered,
                    weights,
                    reference_norm_floor=h_floor,
                ),
            }
            e_delta = observed["E_total"] - reference[f"{key}_E_total"]
            curl_delta = (
                observed["curl_E_total"] - reference[f"{key}_curl_E_total"]
            ) / cfg.k0
            g_delta = np.sqrt(
                np.sum(np.abs(e_delta) ** 2 + np.abs(curl_delta) ** 2, axis=1)
            )
            g_reference = np.sqrt(
                np.sum(
                    np.abs(reference[f"{key}_E_total"]) ** 2
                    + np.abs(reference[f"{key}_curl_E_total"] / cfg.k0) ** 2,
                    axis=1,
                )
            )
            g_difference = float(np.sqrt(np.dot(weights, g_delta**2)))
            g_reference_norm = float(np.sqrt(np.dot(weights, g_reference**2)))
            metrics["G"] = {
                "difference_norm": g_difference,
                "reference_norm": g_reference_norm,
                "relative_with_incident_floor": g_difference
                / max(g_reference_norm, g_floor),
                "incident_floor": g_floor,
            }
            result[key] = metrics
    return result


def _complex_rows(rows: list[dict[str, Any]]) -> np.ndarray:
    return np.asarray(
        [complex(*row["outgoing_amplitude_at_boundary"]) for row in rows],
        dtype=np.complex128,
    )


def _modal_comparison(
    current_rows: list[dict[str, Any]],
    current_metrics: dict[str, Any],
    current_a_volume: float | None,
    reference_run_root: Path,
) -> dict[str, Any]:
    with (reference_run_root / "solve" / "dtn_port_diffraction_orders_3d.json").open(
        encoding="utf-8"
    ) as stream:
        reference_payload = json.load(stream)
    reference_rows = reference_payload["orders"]
    current_keys = [
        (row["side"], int(row["m"]), int(row["n"]), row["polarization"])
        for row in current_rows
    ]
    reference_keys = [
        (row["side"], int(row["m"]), int(row["n"]), row["polarization"])
        for row in reference_rows
    ]
    if current_keys != reference_keys:
        raise ValueError("native and active ordered R13 mode inventories differ")
    current_amplitudes = _complex_rows(current_rows)
    reference_amplitudes = _complex_rows(reference_rows)
    amplitude_difference = current_amplitudes - reference_amplitudes
    group_metrics: dict[str, Any] = {}
    for side in ("top", "bottom"):
        for polarization in ("s", "p"):
            indices = [
                index
                for index, row in enumerate(current_rows)
                if row["side"] == side and row["polarization"] == polarization
            ]
            ref = reference_amplitudes[indices]
            delta = amplitude_difference[indices]
            reference_norm = float(np.linalg.norm(ref))
            difference_norm = float(np.linalg.norm(delta))
            group_metrics[f"{side}_{polarization}"] = {
                "entry_count": len(indices),
                "reference_l2": reference_norm,
                "difference_l2": difference_norm,
                "raw_relative": (
                    difference_norm / reference_norm if reference_norm > 0.0 else None
                ),
                "relative_with_unit_modal_floor": difference_norm
                / max(reference_norm, 1.0),
            }
    channel_power_delta = np.asarray(
        [
            abs(float(row["power_ratio"]) - float(reference_rows[index]["power_ratio"]))
            for index, row in enumerate(current_rows)
        ],
        dtype=np.float64,
    )
    max_power_index = int(np.argmax(channel_power_delta))
    aggregate = {}
    for key in ("R_total", "T_total", "R00_s", "R00_p", "R00_total"):
        current = float(current_metrics[key])
        reference = float(reference_payload["metrics"][key])
        aggregate[key] = {
            "current": current,
            "reference": reference,
            "absolute_difference": abs(current - reference),
        }
    if current_a_volume is not None:
        with (reference_run_root / "task43_h100_anchor_record.json").open(
            encoding="utf-8"
        ) as stream:
            reference_record = json.load(stream)
        reference_a_volume = reference_record["power"]["A_volume_total"]
        aggregate["A_volume_total"] = {
            "current": float(current_a_volume),
            "reference": float(reference_a_volume),
            "absolute_difference": abs(
                float(current_a_volume) - float(reference_a_volume)
            ),
        }
    return {
        "mode_count": len(current_rows),
        "ordered_mode_keys_sha256": _sha256_json(current_keys),
        "ordered_boundary_amplitudes_sha256": _sha256_json(
            [[float(value.real), float(value.imag)] for value in current_amplitudes]
        ),
        "maximum_channel_power_absolute_difference": float(
            channel_power_delta[max_power_index]
        ),
        "maximum_channel_power_difference_mode": list(current_keys[max_power_index]),
        "amplitude_groups": group_metrics,
        "aggregate_power": aggregate,
    }


def _comparison_gates(
    field_metrics: dict[str, Any],
    modal_metrics: dict[str, Any],
) -> dict[str, bool]:
    max_field = max(
        metric["relative_to_reference_or_floor"]
        for order_metrics in field_metrics.values()
        for name, metric in order_metrics.items()
        if name != "G"
    )
    max_g = max(
        order_metrics["G"]["relative_with_incident_floor"]
        for order_metrics in field_metrics.values()
    )
    max_amplitude = max(
        metric["relative_with_unit_modal_floor"]
        for metric in modal_metrics["amplitude_groups"].values()
    )
    max_aggregate_power = max(
        item["absolute_difference"]
        for item in modal_metrics["aggregate_power"].values()
    )
    return {
        "field_and_modal_amplitude_max_relative_le_1e-8": bool(
            max(max_field, max_g, max_amplitude) <= 1.0e-8
        ),
        "aggregate_power_max_absolute_le_1e-8": bool(
            max_aggregate_power <= 1.0e-8
        ),
        "maximum_channel_power_absolute_le_1e-8": bool(
            modal_metrics["maximum_channel_power_absolute_difference"]
            <= 1.0e-8
        ),
    }


def _compare_against_reference(
    *,
    current_rows: list[dict[str, Any]],
    current_port_metrics: dict[str, Any],
    current_a_volume: float,
    current_field_samples: dict[str, Any],
    reference_run_root: Path,
    cfg,
) -> dict[str, Any]:
    field_metrics = _field_comparison(
        current_field_samples,
        reference_run_root / "field_samples_q8_q10.npz",
        cfg,
    )
    modal_metrics = _modal_comparison(
        current_rows,
        current_port_metrics,
        current_a_volume,
        reference_run_root,
    )
    return {
        "field_metrics_q8_q10": field_metrics,
        "modal_metrics": modal_metrics,
        "gates": _comparison_gates(field_metrics, modal_metrics),
    }


def _check_environment(comm: MPI.Intracomm) -> dict[str, Any]:
    local_error = None
    threads = {name: os.environ.get(name) for name in _THREAD_ENV}
    try:
        if os.environ.get("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION") != "1":
            raise RuntimeError("qualified native activation marker is missing")
        if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
            raise RuntimeError(
                f"PETSc scalar type is not complex128: {PETSc.ScalarType}"
            )
        if np.dtype(PETSc.IntType) != np.dtype(np.int64):
            raise RuntimeError(f"PETSc integer type is not int64: {PETSc.IntType}")
        bad_threads = {
            name: value for name, value in threads.items() if value != "1"
        }
        if bad_threads:
            raise RuntimeError(f"math thread counts must all be 1: {bad_threads}")
    except (RuntimeError, TypeError, ValueError) as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    errors = comm.allgather(local_error)
    if any(error is not None for error in errors):
        raise RuntimeError(
            "qualified runtime preflight failed: "
            + "; ".join(
                f"rank {rank}: {error}"
                for rank, error in enumerate(errors)
                if error is not None
            )
        )
    return {
        "python": sys.executable,
        "python_version": sys.version.split()[0],
        "qualified_activation_marker": True,
        "petsc_scalar_type": str(PETSc.ScalarType),
        "petsc_int_type": str(PETSc.IntType),
        "mpi_size": int(comm.size),
        "rank_affinity": comm.allgather(sorted(os.sched_getaffinity(0))),
        "math_threads": threads,
    }


def _write_samples(
    path: Path,
    samples: dict[str, dict[str, np.ndarray]],
    axes: tuple[np.ndarray, ...],
) -> None:
    arrays: dict[str, np.ndarray] = {}
    arrays.update(
        {
            f"axis_{name}_nm": np.asarray(axis, dtype=np.float64)
            for name, axis in zip(("x", "y", "z"), axes, strict=True)
        }
    )
    for key, values in samples.items():
        for name, value in values.items():
            arrays[f"{key}_{name}"] = np.asarray(value)
    np.savez_compressed(path, **arrays)


def _run(
    case: str,
    run_root: Path,
    reference_run_root: Path | None,
    parallel_reference_run_root: Path | None,
) -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    started = time.perf_counter()
    expected_size, kind = _CASES[case]
    if int(comm.size) != expected_size:
        raise RuntimeError(f"case {case} requires MPI size {expected_size}, got {comm.size}")
    _log_stage(comm, started, "preflight", "begin", case_id=case)
    environment = _check_environment(comm)
    root_contract = (
        str(run_root.resolve()),
        None if reference_run_root is None else str(reference_run_root.resolve()),
        None
        if parallel_reference_run_root is None
        else str(parallel_reference_run_root.resolve()),
    )
    root_contracts = comm.allgather(root_contract)
    if any(contract != root_contracts[0] for contract in root_contracts[1:]):
        raise RuntimeError("all MPI ranks must use identical run/reference roots")
    run_root = Path(root_contract[0])
    reference_run_root = (
        None if root_contract[1] is None else Path(root_contract[1])
    )
    parallel_reference_run_root = (
        None
        if root_contract[2] is None
        else Path(root_contract[2])
    )
    root_error = None
    if comm.rank == 0:
        try:
            if run_root.exists() and any(run_root.iterdir()):
                raise FileExistsError(
                    f"refusing to overwrite nonempty output root {run_root}"
                )
            run_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # synchronize a rank-zero filesystem error
            root_error = f"{type(exc).__name__}: {exc}"
    root_error = comm.bcast(root_error, root=0)
    if root_error is not None:
        raise RuntimeError(root_error)
    comm.Barrier()

    reference_identities: dict[str, Any] = {}
    references = []
    if reference_run_root is not None:
        references.append(("native_p3_mpi1", reference_run_root))
    if parallel_reference_run_root is not None:
        references.append(("empty_h_active_p3_mpi1", parallel_reference_run_root))
    for expected_reference, reference_path in references:
        identity = None
        validation_error = None
        if comm.rank == 0:
            try:
                identity = _validate_reference_run(
                    reference_path,
                    expected_case_id=expected_reference,
                )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                validation_error = f"{type(exc).__name__}: {exc}"
        identity, validation_error = comm.bcast(
            (identity, validation_error), root=0
        )
        if validation_error is not None:
            raise RuntimeError(
                f"invalid {expected_reference} reference: {validation_error}"
            )
        reference_identities[expected_reference] = identity
    _log_stage(
        comm,
        started,
        "preflight",
        "end",
        validated_references=sorted(reference_identities),
    )

    source_identity = None
    source_error = None
    if comm.rank == 0:
        try:
            repository = Path(__file__).resolve().parents[2]
            source_hashes = {
                name: _sha256_file(repository / name) for name in _SOURCE_FILES
            }
            source_identity = {
                "git_head": subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repository,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "file_sha256": source_hashes,
            }
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
            source_error = f"{type(exc).__name__}: {exc}"
    source_identity, source_error = comm.bcast((source_identity, source_error), root=0)
    if source_error is not None:
        raise RuntimeError(f"could not capture run source snapshot: {source_error}")
    source_hashes_before = source_identity["file_sha256"]

    cfg = _h100_config(kind=kind, case_name=f"task43_h100_{case}")
    _log_stage(comm, started, "mesh_build", "begin")
    mesh_data = build_airbox_mesh_3d(cfg, run_root / "resolved_mesh")
    axes = _mesh_axes(mesh_data.mesh, comm)
    _assert_h100_mesh(mesh_data, axes)
    reference_axes = None
    if reference_run_root is not None:
        with np.load(
            reference_run_root / "field_samples_q8_q10.npz", allow_pickle=False
        ) as native_reference:
            reference_axes = tuple(
                np.asarray(native_reference[f"axis_{name}_nm"], dtype=np.float64)
                for name in ("x", "y", "z")
            )
    local_h_plan_identity = None
    if kind == "empty_h_active_p3":
        boxes = cell_box_catalog(mesh_data.mesh)
        plan = stage4_local_h_refinement_plan_payload(
            cfg,
            (),
            comm_size=comm.size,
            trace_degree=3,
            cell_interior_degree=6,
            provenance={
                "purpose": "Task43 empty-h active-p3 same-mesh anchor",
                "mesh_role": "resolved boundary-fitted h100 36-cell geometry",
                "active_degree": 3,
                "formal_candidate": False,
            },
            cell_interior_degree_overrides={box: 3 for box in boxes},
            variable_trace_from_cell_degrees=True,
            allow_no_refinement=True,
        )
        if plan["expected_forest"]["leaf_cell_count"] != 36:
            raise RuntimeError("empty-h active plan changed the resolved h100 cell set")
        plan_path = run_root / "empty_h_active_p3_plan.json"
        plan_error = None
        if comm.rank == 0:
            try:
                plan_path.write_text(
                    json.dumps(plan, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            except OSError as exc:
                plan_error = f"{type(exc).__name__}: {exc}"
        plan_error = comm.bcast(plan_error, root=0)
        if plan_error is not None:
            raise RuntimeError(plan_error)
        comm.Barrier()
        cfg.stage4_local_h_refinement_plan = str(plan_path)
        mesh_data = build_stage4_local_h_mesh_data(
            cfg,
            plan_path,
            comm=comm,
        )
        axes = _mesh_axes(mesh_data.mesh, comm)
        _assert_h100_mesh(mesh_data, axes)
        local_h_plan_identity = {
            "plan_sha256": _sha256_file(plan_path),
            "root_cell_count": plan["expected_forest"]["root_cell_count"],
            "leaf_cell_count": plan["expected_forest"]["leaf_cell_count"],
            "marked_root_count": len(plan["marked_root_boxes"]),
            "cell_degree_counts": {
                "p3": len(plan["cell_interior_degrees"]),
                "p4_p5_p6": 0,
            },
            "trace_degree": int(plan["trace_degree"]),
            "cell_interior_degree": int(plan["cell_interior_degree"]),
            "variable_trace_from_cell_degrees": bool(
                plan["variable_trace_from_cell_degrees"]
            ),
            "allow_no_refinement": bool(plan["allow_no_refinement"]),
        }
    _log_stage(
        comm,
        started,
        "mesh_build",
        "end",
        global_cells=int(mesh_data.mesh.topology.index_map(mesh_data.mesh.topology.dim).size_global),
        axis_cell_counts_xyz=[len(axis) - 1 for axis in axes],
        local_h_empty=kind == "empty_h_active_p3",
    )

    backend_audit = resolve_stage4_full3d_assembly_backend(cfg, apply=False)
    expected_backend = (
        STANDARD_FULL_ASSEMBLY_BACKEND
        if kind == "native_p3"
        else ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
    )
    if backend_audit["actual"] != expected_backend:
        raise RuntimeError(f"unexpected assembly backend: {backend_audit}")

    captured: dict[str, Any] = {}

    def capture(field, live_mesh_data, live_cfg, goal_context) -> None:
        captured["fields"] = _field_capture(
            field, live_mesh_data, live_cfg, comm, reference_axes
        )
        modes = goal_context["modes"]
        captured["mode_count"] = len(modes)
        captured["ordered_mode_keys"] = [
            [str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)]
            for mode in modes
        ]

    def native_observer(**kwargs) -> None:
        capture(
            kwargs["field"],
            kwargs["mesh_data"],
            kwargs["config"],
            kwargs["dtn_result"]["goal_context"],
        )
        captured["native_explicit_residual"] = _native_explicit_residual(
            kwargs["linear_system"]
        )
        captured["port_metrics"] = kwargs["dtn_result"]["port_metrics"]

    def active_observer(view) -> None:
        capture(view.field, view.mesh_data, view.config, view.goal_context)
        captured["independent_active_action"] = (
            compute_stage4_independent_active_action(view)
        )
        captured["condensed_residual"] = dict(view.full_active_residual)
        captured["port_metrics"] = dict(view.port_metrics)
        audit = view.mesh_data.local_h_context.audit
        captured["local_h_audit"] = {
            key: audit[key]
            for key in (
                "status",
                "pass",
                "root_cell_count",
                "leaf_cell_count",
                "hanging_patch_count",
                "cell_interior_degree_counts",
                "variable_trace_from_cell_degrees",
                "allow_no_refinement",
            )
        }

    _log_stage(comm, started, "solve_and_observe", "begin")
    summary = run_stage4b_block_grating_3d_case(
        cfg,
        run_root / "solve",
        solution_observer=(native_observer if kind == "native_p3" else None),
        variable_p_live_observer=(
            active_observer if kind == "empty_h_active_p3" else None
        ),
        mesh_data_override=mesh_data,
    )
    _log_stage(comm, started, "solve_and_observe", "end")
    source_paths = {
        name: Path(__file__).resolve().parents[2] / name for name in _SOURCE_FILES
    }
    source_hashes_after = {
        name: _sha256_file(path) for name, path in source_paths.items()
    }
    if source_hashes_before != source_hashes_after:
        raise RuntimeError("a source file changed while the PDE case was running")
    if int(captured.get("mode_count", -1)) != 612:
        raise RuntimeError(f"resolved R13 inventory is not 612 modes: {captured.get('mode_count')}")
    _log_stage(comm, started, "record_and_compare", "begin")
    post_error = None
    if comm.rank == 0:
        record_path = run_root / "task43_h100_anchor_record.json"
        try:
            orders_path = run_root / "solve" / "dtn_port_diffraction_orders_3d.json"
            with orders_path.open(encoding="utf-8") as stream:
                port_payload = json.load(stream)
            rows = port_payload["orders"]
            if len(rows) != 612:
                raise RuntimeError(
                    f"serialized channel output has {len(rows)} rows, expected 612"
                )
            serialized_mode_keys = [
                [row["side"], int(row["m"]), int(row["n"]), row["polarization"]]
                for row in rows
            ]
            if serialized_mode_keys != captured["ordered_mode_keys"]:
                raise RuntimeError(
                    "serialized channels differ from actual ordered mode inventory"
                )
            fields = captured["fields"]
            samples_path = run_root / "field_samples_q8_q10.npz"
            _write_samples(samples_path, fields["samples"], axes)
            a_volume_value = summary.get("A_volume_total")
            if a_volume_value is None or not np.isfinite(float(a_volume_value)):
                raise ValueError("official A_volume_total is missing or non-finite")
            a_volume = float(a_volume_value)

            gates: dict[str, Any] = {
                "solver_completed_and_official": bool(
                    summary.get("case_status") == "completed"
                    and summary.get("official_result") is True
                ),
                "all_612_ordered_modes_present": len(rows) == 612,
            }
            if kind == "native_p3":
                residual = captured["native_explicit_residual"]
                gates["native_explicit_Ax_minus_b_relative_le_1e-9"] = bool(
                    np.isfinite(residual["relative_to_rhs"])
                    and residual["relative_to_rhs"] <= 1.0e-9
                )
            else:
                independent = captured["independent_active_action"][
                    "full_solver_gauge_residual"
                ]
                condensed = captured["condensed_residual"]
                gates["independent_A6_relative_to_rhs_le_1e-9"] = bool(
                    independent["finite"]
                    and np.isfinite(independent["relative_to_independent_rhs"])
                    and independent["relative_to_independent_rhs"] <= 1.0e-9
                )
                gates["condensed_active_residual_le_1e-9"] = bool(
                    np.isfinite(condensed["linear_system_relative_residual"])
                    and condensed["linear_system_relative_residual"] <= 1.0e-9
                )

            comparisons: dict[str, Any] = {}
            if reference_run_root is not None:
                native_comparison = _compare_against_reference(
                    current_rows=rows,
                    current_port_metrics=port_payload["metrics"],
                    current_a_volume=a_volume,
                    current_field_samples=fields["samples"],
                    reference_run_root=reference_run_root,
                    cfg=cfg,
                )
                comparisons["native_p3_mpi1"] = native_comparison
                gates.update(
                    {
                        f"native_p3_{key}": value
                        for key, value in native_comparison["gates"].items()
                    }
                )
            if parallel_reference_run_root is not None:
                parallel_comparison = _compare_against_reference(
                    current_rows=rows,
                    current_port_metrics=port_payload["metrics"],
                    current_a_volume=a_volume,
                    current_field_samples=fields["samples"],
                    reference_run_root=parallel_reference_run_root,
                    cfg=cfg,
                )
                comparisons["empty_h_active_p3_mpi1"] = parallel_comparison
                gates.update(
                    {
                        f"active_mpi1_{key}": value
                        for key, value in parallel_comparison["gates"].items()
                    }
                )

            gates["pass"] = all(value is True for value in gates.values())
            gates["status"] = "passed" if gates["pass"] else "failed"
            record = {
                "schema": "task43.h100_same_mesh_p3_anchor.v1",
                "classification": "G1_same_mesh_component_anchor_not_adaptive_accuracy_claim",
                "case_id": case,
                "method": (
                    "native degree-3 Nedelec, standard_full backend"
                    if kind == "native_p3"
                    else "empty-h p3 active space on p6 carrier, variable-p backend"
                ),
                "environment": environment,
                "resolved_config": cfg.as_jsonable(),
                "numerical_controls": {
                    "assembly_backend": backend_audit,
                    "nedelec_degree": int(cfg.nedelec_degree),
                    "volume_quadrature_degree": int(
                        cfg.stage4_volume_quadrature_degree
                    ),
                    "volume_quadrature_rule": str(
                        cfg.stage4_volume_quadrature_rule
                    ),
                    "incident_and_port_quadrature_degree": int(
                        cfg.stage4_dtn_quadrature_degree
                    ),
                    "sparse_cutoff_policy": str(
                        cfg.stage4_dtn_sparse_cutoff_policy
                    ),
                    "sparse_cutoff_relative_tolerance": float(
                        cfg.stage4_dtn_sparse_cutoff_relative_tolerance
                    ),
                    "port_amplitude_scale_policy": str(
                        cfg.stage4_port_boundary_amplitude_scale_policy
                    ),
                    "mesh": fields["mesh_identity"],
                    "local_h_empty_plan": local_h_plan_identity,
                    "local_h_actual_audit": captured.get("local_h_audit"),
                    "ordered_mode_count": len(rows),
                    "ordered_mode_keys_sha256": _sha256_json(
                        captured["ordered_mode_keys"]
                    ),
                    "field_export": fields["representation"],
                },
                "solver": {
                    "case_status": summary.get("case_status"),
                    "official_result": summary.get("official_result"),
                    "timings_seconds": summary.get("timings_seconds"),
                    "wall_seconds_through_record": time.perf_counter() - started,
                    "explicit_native_residual": captured.get(
                        "native_explicit_residual"
                    ),
                    "condensed_residual": captured.get("condensed_residual"),
                    "independent_active_action": captured.get(
                        "independent_active_action"
                    ),
                },
                "power": {
                    "aggregate": port_payload["metrics"],
                    "A_volume_total": a_volume,
                    "channel_rows_file": str(orders_path),
                    "channel_rows_sha256": _sha256_file(orders_path),
                    "ordered_boundary_amplitudes_sha256": _sha256_json(
                        [row["outgoing_amplitude_at_boundary"] for row in rows]
                    ),
                    "ordered_channel_power_sha256": _sha256_json(
                        [float(row["power_ratio"]) for row in rows]
                    ),
                },
                "field_samples": {
                    "file": str(samples_path),
                    "sha256": _sha256_file(samples_path),
                    "rule_orders": [8, 10],
                    "point_counts": {
                        key: int(values["weights_nm3"].size)
                        for key, values in fields["samples"].items()
                    },
                    "physical_H_from_recovered_curl": True,
                    "scattered_background": "analytic_flat_air_substrate_fresnel",
                    "phase_fit": False,
                },
                "reference_identities": reference_identities,
                "reference_comparison": {
                    "status": "not_run" if not comparisons else "measured",
                    "comparisons": comparisons,
                },
                "gates": gates,
                "source_identity": source_identity,
                "not_run": [
                    "vertical sidewall one-sided mathematical traces",
                    "adaptive selection or accepted h/p updates",
                    "R14 port truncation comparison",
                ],
            }
            record_path.write_text(
                json.dumps(record, indent=2, sort_keys=True, default=_json_default)
                + "\n",
                encoding="utf-8",
            )
            if not gates["pass"]:
                post_error = f"Task43 h100 anchor gates failed; see {record_path}"
            _log_stage(
                comm,
                started,
                "record_and_compare",
                gates["status"],
                record_path=str(record_path),
            )
        except Exception as exc:  # noqa: BLE001 - broadcast rank-zero postsolve failures
            post_error = f"{type(exc).__name__}: {exc}"
            try:
                (run_root / "task43_h100_anchor_postprocess_failure.json").write_text(
                    json.dumps(
                        {
                            "case_id": case,
                            "classification": "postsolve_record_or_comparison_failure",
                            "error": post_error,
                            "elapsed_wall_seconds": time.perf_counter() - started,
                            "source_identity": source_identity,
                        },
                        indent=2,
                        sort_keys=True,
                        default=_json_default,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
    post_error = comm.bcast(post_error, root=0)
    if post_error is not None:
        _log_stage(
            comm,
            started,
            "record_and_compare",
            "failed",
            error=post_error,
        )
        raise RuntimeError(post_error)
    _log_stage(
        comm,
        started,
        "case_complete",
        "end",
        total_wall_seconds=time.perf_counter() - started,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=tuple(_CASES), required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--reference-run-root", type=Path)
    parser.add_argument("--parallel-reference-run-root", type=Path)
    args = parser.parse_args(argv)
    comm = MPI.COMM_WORLD
    expected_size, kind = _CASES[args.case]
    is_native = kind == "native_p3"
    is_mpi2 = args.case == "empty_h_active_p3_mpi2"
    if is_native and (
        args.reference_run_root is not None
        or args.parallel_reference_run_root is not None
    ):
        parser.error("native p3 is the common reference and takes no reference path")
    if not is_native and args.reference_run_root is None:
        parser.error("empty-h active p3 requires --reference-run-root from native_p3_mpi1")
    if is_mpi2 and args.parallel_reference_run_root is None:
        parser.error(
            "MPI2 active p3 requires --parallel-reference-run-root from empty_h_active_p3_mpi1"
        )
    if not is_mpi2 and args.parallel_reference_run_root is not None:
        parser.error("--parallel-reference-run-root is only used by the MPI2 active case")
    if comm.size != expected_size:
        parser.error(f"--case {args.case} requires MPI size {expected_size}")
    summary = _run(
        args.case,
        args.run_root,
        args.reference_run_root,
        args.parallel_reference_run_root,
    )
    if comm.rank == 0:
        print(
            json.dumps(
                {
                    "case_id": args.case,
                    "case_status": summary.get("case_status"),
                    "official_result": summary.get("official_result"),
                    "run_root": str(args.run_root.resolve()),
                },
                sort_keys=True,
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
