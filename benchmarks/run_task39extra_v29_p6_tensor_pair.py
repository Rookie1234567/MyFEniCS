"""Compare the p6 blocked raw-tensor candidate on the live 990-cell mesh.

This component run builds the exact fine mesh/form and local tensor classes,
but it does not build a p4 matrix/factor, solve a PDE, or enter outer KSP.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.io import load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from src.solvers.fullspace_physical_intermediate_runtime import (
    fine_volume_quadrature_metadata,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
from src.solvers.hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
    _cell_integral_kernels,
    _cell_tag_array,
    _tabulate_raw_tensor_class,
)
from src.solvers.task39extra_p6_raw_tensor import Task39ExtraP6RawTensorCandidate
from src.solvers.task40extra_p6_reference_metric import (
    Task40ExtraP6ReferenceMetricCandidate,
)


DEFAULT_INPUT = ROOT / "input/task39extra/v28_fused_kernel_original_h7p5.dat"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(memoryview(np.ascontiguousarray(array)).cast("B")).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _git_facts() -> dict[str, str]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return {
        "head_sha": head,
        "tracked_worktree_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "candidate_solver_sha256": _sha256(
            ROOT / "src/solvers/task39extra_p6_raw_tensor.py"
        ),
        "task40_reference_metric_solver_sha256": _sha256(
            ROOT / "src/solvers/task40extra_p6_reference_metric.py"
        ),
        "pair_runner_sha256": _sha256(Path(__file__).resolve()),
    }


def _form_with_metadata(form: Any, metadata: dict[str, Any]):
    import ufl

    return ufl.Form(
        tuple(
            integral.reconstruct(
                metadata={**(integral.metadata() or {}), **metadata}
            )
            for integral in form.integrals()
        )
    )


def _relative_error(observed: np.ndarray, reference: np.ndarray) -> float:
    denominator = max(float(np.linalg.norm(reference)), np.finfo(float).tiny)
    return float(np.linalg.norm(observed - reference) / denominator)


def _matrix_action_checks(
    reference: np.ndarray, observed: np.ndarray, seed: int
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    vector = rng.normal(size=reference.shape[1]) + 1j * rng.normal(
        size=reference.shape[1]
    )
    reference_action = reference @ vector
    observed_action = observed @ vector
    return {
        "matrix_frobenius_relative": _relative_error(observed, reference),
        "matrix_frobenius_absolute": float(np.linalg.norm(observed - reference)),
        "action_relative": _relative_error(observed_action, reference_action),
        "action_absolute": float(np.linalg.norm(observed_action - reference_action)),
    }


def _local_checks(
    native: np.ndarray,
    candidate: np.ndarray,
    interior_positions: np.ndarray,
    trace_positions: np.ndarray,
    seed: int,
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    dimension = native.shape[0]
    vector = rng.normal(size=dimension) + 1j * rng.normal(size=dimension)
    internal_rhs = rng.normal(size=len(interior_positions)) + 1j * rng.normal(
        size=len(interior_positions)
    )
    trace = rng.normal(size=len(trace_positions)) + 1j * rng.normal(
        size=len(trace_positions)
    )
    matrix_relative = _relative_error(candidate, native)
    native_action = native @ vector
    candidate_action = candidate @ vector
    action_relative = _relative_error(candidate_action, native_action)

    def schur_and_recovery(matrix: np.ndarray):
        Aii = matrix[np.ix_(interior_positions, interior_positions)]
        Ait = matrix[np.ix_(interior_positions, trace_positions)]
        Ati = matrix[np.ix_(trace_positions, interior_positions)]
        Att = matrix[np.ix_(trace_positions, trace_positions)]
        factor = lu_factor(Aii, check_finite=False)
        interior_from_trace = -lu_solve(factor, Ait, check_finite=False)
        schur = Att + Ati @ interior_from_trace
        recovered = lu_solve(
            factor,
            internal_rhs - Ait @ trace,
            check_finite=False,
        )
        residual = Aii @ recovered + Ait @ trace - internal_rhs
        closure = _relative_error(residual, internal_rhs)
        return schur, interior_from_trace, recovered, closure, residual

    (
        native_schur,
        native_recovery,
        native_solution,
        native_closure,
        native_rhs_residual,
    ) = schur_and_recovery(native)
    (
        candidate_schur,
        candidate_recovery,
        candidate_solution,
        candidate_closure,
        candidate_rhs_residual,
    ) = schur_and_recovery(candidate)
    return {
        "matrix_frobenius_relative": matrix_relative,
        "matrix_frobenius_absolute": float(np.linalg.norm(candidate - native)),
        "action_relative": action_relative,
        "action_absolute": float(np.linalg.norm(candidate_action - native_action)),
        "schur_relative": _relative_error(candidate_schur, native_schur),
        "schur_absolute": float(np.linalg.norm(candidate_schur - native_schur)),
        "recovery_map_relative": _relative_error(candidate_recovery, native_recovery),
        "recovery_map_absolute": float(np.linalg.norm(candidate_recovery - native_recovery)),
        "nonzero_rhs_recovery_solution_relative": _relative_error(
            candidate_solution, native_solution
        ),
        "nonzero_rhs_recovery_solution_absolute": float(
            np.linalg.norm(candidate_solution - native_solution)
        ),
        "native_nonzero_rhs_recovery_closure": native_closure,
        "native_nonzero_rhs_recovery_closure_absolute": float(
            np.linalg.norm(native_rhs_residual)
        ),
        "candidate_nonzero_rhs_recovery_closure": candidate_closure,
        "candidate_nonzero_rhs_recovery_closure_absolute": float(
            np.linalg.norm(candidate_rhs_residual)
        ),
    }


def _task40_ffcx_representatives(
    local_classes: dict[tuple[Any, ...], np.ndarray],
    boundary_classes: dict[str, set[tuple[Any, ...]]],
    air_tag: int,
) -> dict[tuple[Any, ...], list[str]]:
    """Bound original-FFCx work to material, boundary, gap, and round-key cases."""

    selected: dict[tuple[Any, ...], set[str]] = {}

    def add(key: tuple[Any, ...], reason: str) -> None:
        selected.setdefault(key, set()).add(reason)

    keys = sorted(local_classes)
    for tag in sorted({int(key[0]) for key in keys}):
        candidates = [key for key in keys if int(key[0]) == tag]
        add(candidates[0], f"material_tag_{tag}")

    for boundary, candidates in sorted(boundary_classes.items()):
        if candidates:
            add(sorted(candidates)[0], boundary)

    air_classes = [key for key in keys if int(key[0]) == int(air_tag)]
    for axis, axis_name in enumerate(("x", "y", "z")):
        if air_classes:
            key = min(air_classes, key=lambda item: (float(item[1 + axis]), item))
            add(key, f"air_narrow_width_{axis_name}")

    old_key_groups: dict[tuple[Any, ...], list[tuple[Any, ...]]] = {}
    for key in keys:
        rounded = tuple(float(np.round(value, 12)) for value in key[1:])
        old_key_groups.setdefault((int(key[0]), rounded), []).append(key)
    for group in old_key_groups.values():
        exact_widths = {tuple(key[1:]) for key in group}
        if len(exact_widths) > 1:
            for key in sorted(group)[:2]:
                add(key, "distinct_exact_widths_collide_under_old_round12_key")
            break

    return {key: sorted(reasons) for key, reasons in sorted(selected.items())}


def _task40_matrix_gate(checks: dict[str, float]) -> bool:
    return bool(
        checks["matrix_frobenius_relative"] <= 1.0e-10
        and checks["action_relative"] <= 1.0e-11
    )


def _task40_local_gate(checks: dict[str, float]) -> bool:
    return bool(
        _task40_matrix_gate(checks)
        and checks["schur_relative"] <= 1.0e-8
        and checks["recovery_map_relative"] <= 1.0e-8
        and checks["nonzero_rhs_recovery_solution_relative"] <= 1.0e-8
        and checks["native_nonzero_rhs_recovery_closure"] <= 1.0e-10
        and checks["candidate_nonzero_rhs_recovery_closure"] <= 1.0e-10
    )


def _run_task40_p2_trial(
    *,
    result: dict[str, Any],
    partial_path: Path,
    output_path: Path,
    input_path: Path,
    local_classes: dict[tuple[Any, ...], np.ndarray],
    orientation_by_class: dict[tuple[Any, ...], int],
    boundary_classes: dict[str, set[tuple[Any, ...]]],
    cfg: Any,
    full_form: Any,
    compiled: Any,
    kernels: dict[int, Any],
    space: Any,
    campaign_started: float,
) -> dict[str, Any]:
    """Compare blocked-Gram and shared-reference candidates on real type keys."""

    from src.solvers.hcurl_assembly_time_condensation import _orient_cell_tensor

    ordered_keys = sorted(local_classes)
    ffcx_samples = _task40_ffcx_representatives(
        local_classes,
        boundary_classes,
        int(cfg.tags.air),
    )
    result["ffcx_sample_selection"] = [
        {
            "material_tag": int(key[0]),
            "cell_widths": [float(value) for value in key[1:]],
            "reasons": reasons,
            "orientation_info": int(orientation_by_class[key]),
        }
        for key, reasons in ffcx_samples.items()
    ]
    print(
        f"TASK40_P2_FFCX_SAMPLE_COUNT {len(ffcx_samples)}/{len(ordered_keys)}",
        flush=True,
    )
    result["task40_p2_contract"] = {
        "full_real_class_count": len(ordered_keys),
        "full_class_scope": "blocked-Gram vs reference-metric matrix/action, every exact G0/G1 raw class",
        "original_ffcx_scope": "bounded material/boundary/narrow-air/round12-collision representatives only",
        "matrix_relative_limit": 1.0e-10,
        "action_relative_limit": 1.0e-11,
        "schur_rhs_relative_limit": 1.0e-8,
        "strict_identity_limit": 1.0e-10,
        "paired_rounds_max": 3,
        "full_global_factor_or_pde": False,
    }
    _write_json(partial_path, result)

    interior = np.asarray(space.element.basix_element.entity_dofs[3][0], dtype=np.int32)
    trace = np.setdiff1d(
        np.arange(int(space.element.space_dimension), dtype=np.int32), interior
    )
    baseline_type = Task39ExtraP6RawTensorCandidate
    candidate_type = Task40ExtraP6ReferenceMetricCandidate
    round_records: list[dict[str, Any]] = []
    class_records = {
        key: {
            "material_tag": int(key[0]),
            "cell_widths": [float(value) for value in key[1:]],
            "orientation_info": int(orientation_by_class[key]),
            "rounds": [],
            "ffcx_sample_reasons": ffcx_samples.get(key, []),
        }
        for key in ordered_keys
    }
    all_numerics_pass = True
    comparison_started = time.perf_counter()

    for round_index in range(1, 4):
        round_started = time.perf_counter()
        order = ("blocked_gram", "reference_metric") if round_index % 2 else (
            "reference_metric",
            "blocked_gram",
        )
        builders: dict[str, Any] = {}
        initialization_seconds: dict[str, float] = {}
        for name in order:
            builder_type = baseline_type if name == "blocked_gram" else candidate_type
            started = time.perf_counter()
            builders[name] = builder_type(
                space.element.basix_element,
                cfg,
                full_form,
                compiled_form=compiled,
            )
            initialization_seconds[name] = float(time.perf_counter() - started)

        totals = {
            "blocked_gram_seconds": initialization_seconds["blocked_gram"],
            "reference_metric_seconds": initialization_seconds["reference_metric"],
            "blocked_orientation_seconds": 0.0,
            "reference_orientation_seconds": 0.0,
            "ffcx_seconds": 0.0,
        }
        round_pass = True
        for class_index, key in enumerate(ordered_keys, start=1):
            matrices: dict[str, np.ndarray] = {}
            build_seconds: dict[str, float] = {}
            for name in order:
                started = time.perf_counter()
                matrices[name] = builders[name](
                    compiled,
                    kernels,
                    local_classes[key],
                    tag=int(key[0]),
                    dimension=int(space.element.space_dimension),
                )
                build_seconds[name] = float(time.perf_counter() - started)
                totals[
                    "blocked_gram_seconds"
                    if name == "blocked_gram"
                    else "reference_metric_seconds"
                ] += build_seconds[name]

            blocked_matrix = matrices["blocked_gram"]
            candidate_matrix = matrices["reference_metric"]
            raw_pair = _matrix_action_checks(
                blocked_matrix, candidate_matrix, 91000 + class_index
            )
            class_pass = _task40_matrix_gate(raw_pair)
            sample_facts = None
            if round_index == 1 and key in ffcx_samples:
                ffcx_started = time.perf_counter()
                native_matrix = _tabulate_raw_tensor_class(
                    compiled,
                    kernels,
                    local_classes[key],
                    tag=int(key[0]),
                    dimension=int(space.element.space_dimension),
                )
                ffcx_seconds = float(time.perf_counter() - ffcx_started)
                totals["ffcx_seconds"] += ffcx_seconds
                sample_facts = {
                    "ffcx_seconds": ffcx_seconds,
                    "ffcx_vs_blocked_raw": _matrix_action_checks(
                        native_matrix, blocked_matrix, 92000 + class_index
                    ),
                    "ffcx_vs_reference_metric_raw": _matrix_action_checks(
                        native_matrix, candidate_matrix, 93000 + class_index
                    ),
                }
            orientation = int(orientation_by_class[key])
            for name in order:
                started = time.perf_counter()
                _orient_cell_tensor(
                    space.element,
                    matrices[name],
                    np.asarray([orientation], dtype=np.uint32),
                )
                elapsed = float(time.perf_counter() - started)
                totals[
                    "blocked_orientation_seconds"
                    if name == "blocked_gram"
                    else "reference_orientation_seconds"
                ] += elapsed

            oriented_pair = _matrix_action_checks(
                blocked_matrix, candidate_matrix, 94000 + class_index
            )
            class_pass = class_pass and _task40_matrix_gate(oriented_pair)
            if sample_facts is not None:
                _orient_cell_tensor(
                    space.element,
                    native_matrix,
                    np.asarray([orientation], dtype=np.uint32),
                )
                checks = {
                    "blocked_vs_reference_metric": _local_checks(
                        blocked_matrix,
                        candidate_matrix,
                        interior,
                        trace,
                        95000 + class_index,
                    ),
                    "ffcx_vs_blocked": _local_checks(
                        native_matrix,
                        blocked_matrix,
                        interior,
                        trace,
                        96000 + class_index,
                    ),
                    "ffcx_vs_reference_metric": _local_checks(
                        native_matrix,
                        candidate_matrix,
                        interior,
                        trace,
                        97000 + class_index,
                    ),
                }
                sample_facts["oriented_local_checks"] = checks
                sample_pass = all(_task40_local_gate(check) for check in checks.values())
                if not _task40_matrix_gate(sample_facts["ffcx_vs_blocked_raw"]):
                    sample_pass = False
                if not _task40_matrix_gate(sample_facts["ffcx_vs_reference_metric_raw"]):
                    sample_pass = False
                class_pass = class_pass and sample_pass
                del native_matrix

            class_record = {
                "round": round_index,
                "first_builder": order[0],
                "blocked_build_seconds": build_seconds["blocked_gram"],
                "reference_metric_build_seconds": build_seconds["reference_metric"],
                "blocked_matrix_sha256": _array_sha256(blocked_matrix),
                "reference_metric_matrix_sha256": _array_sha256(candidate_matrix),
                "raw_matrix_action": raw_pair,
                "oriented_matrix_action": oriented_pair,
                "ffcx_sample": sample_facts,
                "passed": bool(class_pass),
            }
            class_records[key]["rounds"].append(class_record)
            round_pass = round_pass and class_pass
            del matrices

        blocked_audit = builders["blocked_gram"].audit()
        candidate_audit = builders["reference_metric"].audit()
        totals["blocked_total_including_initialization_and_orientation_seconds"] = (
            totals["blocked_gram_seconds"] + totals["blocked_orientation_seconds"]
        )
        totals["reference_total_including_initialization_and_orientation_seconds"] = (
            totals["reference_metric_seconds"]
            + totals["reference_orientation_seconds"]
        )
        totals["candidate_over_blocked_ratio"] = float(
            totals["reference_total_including_initialization_and_orientation_seconds"]
            / max(
                totals["blocked_total_including_initialization_and_orientation_seconds"],
                np.finfo(float).tiny,
            )
        )
        round_record = {
            "round": round_index,
            "first_builder": order[0],
            "blocked_initialization_seconds": initialization_seconds["blocked_gram"],
            "reference_metric_initialization_seconds": initialization_seconds[
                "reference_metric"
            ],
            **totals,
            "blocked_workspace_bytes_upper": int(blocked_audit["workspace_bytes_upper"]),
            "reference_metric_workspace_bytes_upper": int(
                candidate_audit["workspace_bytes_upper"]
            ),
            "reference_template_bytes": int(
                candidate_audit["template_unique_backing_bytes"]
            ),
            "reference_template_backing_count": int(
                candidate_audit["template_unique_backing_count"]
            ),
            "template_initialization_workspace_bytes_upper": int(
                candidate_audit["template_initialization_workspace_bytes_upper"]
            ),
            "metric_composition_workspace_bytes_upper": int(
                candidate_audit["metric_composition_workspace_bytes_upper"]
            ),
            "round_wall_seconds": float(time.perf_counter() - round_started),
            "round_numerics_passed": bool(round_pass),
        }
        round_records.append(round_record)
        all_numerics_pass = all_numerics_pass and round_pass
        result["candidate_analysis"] = candidate_audit
        result["blocked_gram_analysis"] = blocked_audit
        result["paired_rounds"] = round_records
        result["classes_completed"] = [
            {
                key_name: value
                for key_name, value in record.items()
                if key_name != "rounds"
            }
            | {"rounds": record["rounds"]}
            for _key, record in sorted(class_records.items())
        ]
        result["sum_paired_backend_seconds"] = float(
            sum(
                round_item[
                    "blocked_total_including_initialization_and_orientation_seconds"
                ]
                + round_item[
                    "reference_total_including_initialization_and_orientation_seconds"
                ]
                for round_item in round_records
            )
        )
        _write_json(partial_path, result)
        print(
            "TASK40_P2_ROUND "
            f"{round_index}/3 classes={len(ordered_keys)} ffcx_samples={len(ffcx_samples)} "
            f"blocked={round_record['blocked_total_including_initialization_and_orientation_seconds']:.3f}s "
            f"reference_metric={round_record['reference_total_including_initialization_and_orientation_seconds']:.3f}s "
            f"ratio={round_record['candidate_over_blocked_ratio']:.4f} pass={round_pass}",
            flush=True,
        )
        del builders

    round_ratios = [float(item["candidate_over_blocked_ratio"]) for item in round_records]
    repeatable_gain = bool(round_ratios and all(ratio < 1.0 for ratio in round_ratios))
    memory_delta = max(
        0,
        int(round_records[-1]["reference_metric_workspace_bytes_upper"])
        - int(round_records[-1]["blocked_workspace_bytes_upper"]),
    )
    historical_g1_peak = 6_855_741_440
    projected_g1_peak = historical_g1_peak + memory_delta
    numerics_gate = bool(
        all_numerics_pass
        and len(class_records) == len(ordered_keys)
        and all(len(record["rounds"]) == 3 for record in class_records.values())
    )
    result["component_peak_rss_bytes"] = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    result["paired_comparison_wall_seconds"] = float(
        time.perf_counter() - comparison_started
    )
    result["component_campaign_wall_seconds"] = float(
        time.perf_counter() - campaign_started
    )
    result["orientation_transform_contract"] = {
        "path": "src.solvers.hcurl_assembly_time_condensation._orient_cell_tensor",
        "transform": "T A T^T using two existing Basix T_apply calls",
        "transforms_measured_for_every_raw_class_each_round": True,
        "single_transpose_scratch_bytes_upper": int(
            int(space.element.space_dimension) ** 2 * np.dtype(np.complex128).itemsize
        ),
    }
    result["qualification"] = {
        "numerically_qualified": numerics_gate,
        "all_g0_g1_exact_class_matrix_action_checks_pass": numerics_gate,
        "repeatable_overall_gain_vs_blocked_gram": repeatable_gain,
        "candidate_over_blocked_ratios_including_initialization_and_orientation": round_ratios,
        "memory_gate_status": "pending actual G1 M0 user-service and independent-watchdog run",
        "memory_gate_kind": "component RSS, six-template backing, and scratch upper bounds are reported; the full solver RSS is not inferred",
        "historical_g1_peak_rss_bytes": historical_g1_peak,
        "workspace_delta_bytes_upper_bound": memory_delta,
        "projected_g1_peak_rss_bytes_scenario_only": projected_g1_peak,
        "adopt_candidate": False,
        "eligible_for_g1_m0_watchdog_trial": bool(numerics_gate and repeatable_gain),
        "full_run_requires_user_service_and_independent_watchdog": True,
        "matrix_relative_limit": 1.0e-10,
        "action_relative_limit": 1.0e-11,
        "schur_and_recovery_limit": 1.0e-8,
        "strict_identity_limit": 1.0e-10,
    }
    result["status"] = (
        "COMPONENT_QUALIFIED_FOR_G1_M0_WATCHDOG_TRIAL"
        if result["qualification"]["eligible_for_g1_m0_watchdog_trial"]
        else "NOT_QUALIFIED"
    )
    result["official_pde"] = False
    result["global_p4_matrix_or_factor"] = False
    _write_json(output_path, result)
    partial_path.unlink()
    return result


def run(
    input_path: Path,
    output_path: Path,
    *,
    candidate_kind: str = "task39_blocked_gram",
    preserve_exact_geometry: bool = False,
    allow_other_mesh: bool = False,
) -> dict[str, Any]:
    if candidate_kind not in {"task39_blocked_gram", "task40_reference_metric"}:
        raise ValueError(f"unsupported p6 tensor candidate {candidate_kind!r}")
    if candidate_kind == "task40_reference_metric" and not preserve_exact_geometry:
        raise ValueError("Task40 reference-metric trials must preserve exact geometry")
    if output_path.exists() or output_path.with_suffix(output_path.suffix + ".partial").exists():
        raise FileExistsError(f"refusing to overwrite p6 tensor evidence at {output_path}")
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("the reviewed p6 tensor component pair is MPI1-only")
    source_sha = _git_facts()
    result: dict[str, Any] = {
        "schema": "task39extra.v29.p6-raw-tensor-pair.v1",
        "status": "STARTED",
        "candidate_kind": candidate_kind,
        "preserve_exact_geometry": bool(preserve_exact_geometry),
        "official_pde": False,
        "global_p4_matrix_or_factor": False,
        "input_path": str(input_path.resolve()),
        "input_sha256": _sha256(input_path),
        "source": source_sha,
        "classes_completed": [],
        "qualification": {"adopt_candidate": False},
    }
    partial_path = output_path.with_suffix(output_path.suffix + ".partial")
    _write_json(partial_path, result)
    try:
        resolved = load_and_resolve(input_path)
        result["physical_model_sha256"] = resolved.physical_model_sha256
        cfg = simulation_config_3d_from_normalized(resolved.as_jsonable())
        if int(cfg.nedelec_degree) != 6:
            raise ValueError("p6 tensor pair requires a p6 input")
        if (
            not allow_other_mesh
            and tuple(cfg.mesh_axis_cell_counts_requested) != (9, 5, 22)
        ):
            raise ValueError("input differs from the frozen 990-cell h7.5 mesh")

        campaign_started = time.perf_counter()
        started = time.perf_counter()
        levels = _build_same_mesh_levels(
            cfg,
            MPI.COMM_WORLD,
            (6,),
            include_positive_coefficients=False,
        )
        result["mesh_build_seconds"] = float(time.perf_counter() - started)
        result["owned_cell_count"] = int(levels["mesh"].topology.index_map(3).size_local)

        quadrature_metadata, quadrature_records = fine_volume_quadrature_metadata(
            levels, cfg
        )
        result["official_split_quadrature_metadata"] = [dict(item) for item in quadrature_metadata]
        result["official_split_quadrature_records"] = list(quadrature_records)

        import ufl
        from dolfinx import fem
        from src.solvers.common_3d_forms import _build_physical_volume_terms

        space = levels["spaces"][6]
        mesh = levels["mesh"]
        dx = ufl.Measure("dx", domain=mesh, subdomain_data=levels["mesh_data"].cell_tags)
        curl_form, mass_form = _build_physical_volume_terms(
            cfg, ufl.TrialFunction(space), ufl.TestFunction(space), dx
        )
        curl_form = _form_with_metadata(curl_form, dict(quadrature_metadata[0]))
        mass_form = _form_with_metadata(mass_form, dict(quadrature_metadata[1]))
        full_form = curl_form + mass_form
        form_started = time.perf_counter()
        compiled = fem.form(full_form, jit_options=dict(SAME_MESH_JIT_OPTIONS))
        result["complete_form_compile_seconds"] = float(time.perf_counter() - form_started)
        result["ufcx_form_signature"] = compiled.module.ffi.string(
            compiled.ufcx_form.signature
        ).decode("ascii")
        kernels = _cell_integral_kernels(
            compiled, sum_duplicate_cell_integrals=True
        )
        result["ffcx_kernel_inventory"] = {
            str(tag): len(value) if isinstance(value, (tuple, list)) else 1
            for tag, value in sorted(kernels.items())
        }
        builder = None
        if candidate_kind == "task39_blocked_gram":
            builder_started = time.perf_counter()
            builder = Task39ExtraP6RawTensorCandidate(
                space.element.basix_element,
                cfg,
                full_form,
                compiled_form=compiled,
            )
            result["candidate_builder_initialization_seconds"] = float(
                time.perf_counter() - builder_started
            )
            result["candidate_analysis"] = builder.audit()

        tags = _cell_tag_array(
            levels["mesh_data"].cell_tags,
            int(mesh.topology.index_map(3).size_local),
        )
        mesh.topology.create_entity_permutations()
        cell_permutations = np.asarray(
            mesh.topology.get_cell_permutation_info(), dtype=np.uint32
        )
        global_lower = np.min(mesh.geometry.x, axis=0)
        global_upper = np.max(mesh.geometry.x, axis=0)
        local_classes: dict[tuple[Any, ...], np.ndarray] = {}
        orientation_ids_by_class: dict[tuple[Any, ...], set[int]] = {}
        boundary_classes: dict[str, set[tuple[Any, ...]]] = {}
        for cell in range(len(tags)):
            geometry_dofs = np.asarray(mesh.geometry.dofmap[cell], dtype=np.int32)
            physical_coordinates = np.asarray(
                mesh.geometry.x[geometry_dofs], dtype=np.float64
            )
            cell_lower = physical_coordinates.min(axis=0)
            cell_upper = physical_coordinates.max(axis=0)
            coordinates, widths = _canonical_axis_aligned_coordinates(
                mesh,
                cell,
                tolerance=1.0e-11,
                preserve_exact_geometry=preserve_exact_geometry,
            )
            key = (int(tags[cell]), *widths)
            previous = local_classes.get(key)
            if previous is not None and not np.array_equal(previous, coordinates):
                raise RuntimeError(f"live mesh class {key!r} has inconsistent canonical geometry")
            local_classes.setdefault(key, coordinates)
            orientation_ids_by_class.setdefault(key, set()).add(
                int(cell_permutations[cell])
            )
            for axis, axis_name in enumerate(("x", "y", "z")):
                if cell_lower[axis] == global_lower[axis]:
                    boundary_classes.setdefault(
                        f"domain_boundary_{axis_name}_min", set()
                    ).add(key)
                if cell_upper[axis] == global_upper[axis]:
                    boundary_classes.setdefault(
                        f"domain_boundary_{axis_name}_max", set()
                    ).add(key)
        result["raw_class_count"] = len(local_classes)
        result["oriented_class_count"] = int(
            sum(len(values) for values in orientation_ids_by_class.values())
        )
        result["cell_count_to_raw_class_ratio"] = float(
            len(tags) / max(len(local_classes), 1)
        )

        if candidate_kind == "task40_reference_metric":
            if not preserve_exact_geometry:
                raise ValueError("Task40 P2 requires exact, unrounded cell widths")
            orientation_by_class = {
                key: min(values) for key, values in orientation_ids_by_class.items()
            }
            return _run_task40_p2_trial(
                result=result,
                partial_path=partial_path,
                output_path=output_path,
                input_path=input_path,
                local_classes=local_classes,
                orientation_by_class=orientation_by_class,
                boundary_classes=boundary_classes,
                cfg=cfg,
                full_form=full_form,
                compiled=compiled,
                kernels=kernels,
                space=space,
                campaign_started=campaign_started,
            )

        basix_element = space.element.basix_element
        interior = np.asarray(basix_element.entity_dofs[3][0], dtype=np.int32)
        trace = np.setdiff1d(np.arange(int(space.element.space_dimension), dtype=np.int32), interior)
        started_pair = time.perf_counter()
        passed = True
        for index, key in enumerate(sorted(local_classes), start=1):
            tag, *widths = key
            coordinates = local_classes[key]
            native_started = time.perf_counter()
            native = _tabulate_raw_tensor_class(
                compiled,
                kernels,
                coordinates,
                tag=int(tag),
                dimension=int(space.element.space_dimension),
            )
            native_seconds = float(time.perf_counter() - native_started)
            candidate_started = time.perf_counter()
            candidate = builder(
                compiled,
                kernels,
                coordinates,
                tag=int(tag),
                dimension=int(space.element.space_dimension),
            )
            candidate_seconds = float(time.perf_counter() - candidate_started)
            checks = _local_checks(native, candidate, interior, trace, 39000 + index)
            class_pass = (
                checks["matrix_frobenius_relative"] <= 1.0e-10
                and checks["action_relative"] <= 1.0e-10
                and checks["schur_relative"] <= 1.0e-8
                and checks["recovery_map_relative"] <= 1.0e-8
                and checks["nonzero_rhs_recovery_solution_relative"] <= 1.0e-8
                and checks["native_nonzero_rhs_recovery_closure"] <= 1.0e-8
                and checks["candidate_nonzero_rhs_recovery_closure"] <= 1.0e-8
            )
            passed = passed and class_pass
            record = {
                "index": index,
                "class_key": {"tag": int(tag), "cell_widths": [float(x) for x in widths]},
                "native_ffcx_seconds": native_seconds,
                "candidate_seconds": candidate_seconds,
                "native_matrix_sha256": _array_sha256(native),
                "candidate_matrix_sha256": _array_sha256(candidate),
                "checks": checks,
                "passed": class_pass,
            }
            result["classes_completed"].append(record)
            result["elapsed_pair_seconds"] = float(time.perf_counter() - started_pair)
            result["qualification"] = {
                "all_completed_classes_pass": passed,
                "matrix_relative_limit": 1.0e-10,
                "action_relative_limit": 1.0e-10,
                "schur_and_recovery_limit": 1.0e-8,
                "adopt_candidate": False,
            }
            _write_json(partial_path, result)
            print(
                "P3_CLASS "
                f"{index}/{len(local_classes)} tag={tag} widths={tuple(widths)} "
                f"native={native_seconds:.6f}s candidate={candidate_seconds:.6f}s "
                f"matrix_rel={checks['matrix_frobenius_relative']:.3e} "
                f"schur_rel={checks['schur_relative']:.3e} pass={class_pass}",
                flush=True,
            )
            del native, candidate

        candidate_times = [row["candidate_seconds"] for row in result["classes_completed"]]
        native_times = [row["native_ffcx_seconds"] for row in result["classes_completed"]]
        result["timing_summary"] = {
            "native_all_classes_seconds": float(sum(native_times)),
            "candidate_all_classes_seconds": float(sum(candidate_times)),
            "candidate_all_classes_with_initialization_seconds": float(
                sum(candidate_times) + result["candidate_builder_initialization_seconds"]
            ),
            "all_class_ratio_candidate_over_native": float(
                sum(candidate_times) / max(sum(native_times), np.finfo(float).tiny)
            ),
            "native_seconds_by_class": native_times,
            "candidate_seconds_by_class": candidate_times,
        }
        result["candidate_analysis"] = builder.audit()
        representative = result["classes_completed"][0]
        representative_key = sorted(local_classes)[0]
        representative_coordinates = local_classes[representative_key]
        representative_tag = int(representative_key[0])
        representative_pairs = [
            {
                "repeat": 1,
                "native_ffcx_seconds": representative["native_ffcx_seconds"],
                "candidate_seconds": representative["candidate_seconds"],
                "first_call": "native_then_candidate",
            }
        ]
        for repeat, order in (
            (2, ("candidate", "native")),
            (3, ("native", "candidate")),
        ):
            sample = {"repeat": repeat, "first_call": f"{order[0]}_then_{order[1]}"}
            for implementation in order:
                call_started = time.perf_counter()
                if implementation == "native":
                    tensor = _tabulate_raw_tensor_class(
                        compiled,
                        kernels,
                        representative_coordinates,
                        tag=representative_tag,
                        dimension=int(space.element.space_dimension),
                    )
                    sample["native_ffcx_seconds"] = float(
                        time.perf_counter() - call_started
                    )
                else:
                    tensor = builder(
                        compiled,
                        kernels,
                        representative_coordinates,
                        tag=representative_tag,
                        dimension=int(space.element.space_dimension),
                    )
                    sample["candidate_seconds"] = float(
                        time.perf_counter() - call_started
                    )
                del tensor
            representative_pairs.append(sample)
        result["representative_paired_timing"] = {
            "class_key": dict(representative["class_key"]),
            "samples": representative_pairs,
            "native_median_seconds": float(
                np.median([row["native_ffcx_seconds"] for row in representative_pairs])
            ),
            "candidate_median_seconds": float(
                np.median([row["candidate_seconds"] for row in representative_pairs])
            ),
        }
        result["candidate_workspace_bytes_upper"] = int(builder.workspace_bytes_upper)
        result["process_peak_rss_bytes"] = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
        numerical_pass = bool(
            passed and len(result["classes_completed"]) == len(local_classes)
        )
        all_class_speed_gain = bool(
            result["timing_summary"]["candidate_all_classes_seconds"]
            < result["timing_summary"]["native_all_classes_seconds"]
        )
        representative_speed_gain = bool(
            result["representative_paired_timing"]["candidate_median_seconds"]
            < result["representative_paired_timing"]["native_median_seconds"]
        )
        result["qualification"] = {
            "numerically_qualified": numerical_pass,
            "all_completed_classes_pass": numerical_pass,
            "all_class_speed_gain": all_class_speed_gain,
            "representative_speed_gain": representative_speed_gain,
            "matrix_relative_limit": 1.0e-10,
            "action_relative_limit": 1.0e-10,
            "schur_and_recovery_limit": 1.0e-8,
            "adopt_candidate": bool(
                numerical_pass and all_class_speed_gain and representative_speed_gain
            ),
        }
        result["status"] = (
            "QUALIFIED"
            if result["qualification"]["adopt_candidate"]
            else "NOT_QUALIFIED"
        )
        result["official_pde"] = False
        _write_json(output_path, result)
        partial_path.unlink()
        return result
    except BaseException as error:
        result["status"] = "FAILED_OR_UNSUPPORTED"
        result["failure"] = f"{type(error).__name__}: {error}"
        _write_json(partial_path, result)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--candidate-kind",
        choices=("task39_blocked_gram", "task40_reference_metric"),
        default="task39_blocked_gram",
    )
    parser.add_argument("--preserve-exact-geometry", action="store_true")
    parser.add_argument("--allow-other-mesh", action="store_true")
    args = parser.parse_args()
    result = run(
        args.input,
        args.output,
        candidate_kind=args.candidate_kind,
        preserve_exact_geometry=args.preserve_exact_geometry,
        allow_other_mesh=args.allow_other_mesh,
    )
    print(
        "P3_RESULT "
        f"{args.output} status={result['status']} "
        f"adopt_candidate={result['qualification']['adopt_candidate']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
