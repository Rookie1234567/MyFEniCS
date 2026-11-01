#!/usr/bin/env python3
"""Bounded actual-mesh cache-key and local P6 quadrature QA for gate_cd.

This diagnostic builds the mapped mesh and P6 space, counts the production
mapped-cell cache classes, and compiles only a two/three-cell submesh form.
It tabulates local element tensors and local Schur/recovery blocks only. It
does not assemble a model/global matrix, build a global factor, or solve.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
import traceback
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INPUT = ROOT / "input/task40_gate_cd/gate_cd_0p7_mapped_p6_staged.dat"
HOST_AVAILABLE_FLOOR_BYTES = 64 * 1024**3
EXPECTED_PROFILE = "task40_gate_cd_0p7_mapped_p6_direct_v1"
QUADRATURE_DEGREES = (15, 21, 27)
_ACTIVE_PAYLOAD: dict[str, Any] | None = None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value: Any) -> Any:
    from collections.abc import Mapping

    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (complex, np.complexfloating)):
        number = complex(value)
        return [float(number.real), float(number.imag)]
    if isinstance(value, np.ndarray):
        return {
            "shape": [int(item) for item in value.shape],
            "dtype": str(value.dtype),
            "sha256": hashlib.sha256(
                np.ascontiguousarray(value).view(np.uint8).tobytes()
            ).hexdigest(),
        }
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"cannot serialize QA value of type {type(value).__name__}")


def _read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
        key, raw = line.split(":", 1)
        if key in {"MemAvailable", "SwapTotal", "SwapFree"}:
            values[key] = int(raw.strip().split()[0]) * 1024
    return values


def _numa_maps_summary() -> dict[str, int]:
    counts = {
        "interleave_0_1_mappings": 0,
        "default_mappings": 0,
        "local_mappings": 0,
        "other_policy_mappings": 0,
        "unclassified_policy_mappings": 0,
    }
    for line in Path("/proc/self/numa_maps").read_text(encoding="ascii").splitlines():
        fields = line.split()
        if len(fields) < 2:
            counts["unclassified_policy_mappings"] += 1
            continue
        policy = fields[1]
        if policy == "interleave:0-1":
            counts["interleave_0_1_mappings"] += 1
        elif policy == "default":
            counts["default_mappings"] += 1
        elif policy == "local":
            counts["local_mappings"] += 1
        elif policy.startswith(("bind:", "prefer:", "interleave:")):
            counts["other_policy_mappings"] += 1
        else:
            counts["unclassified_policy_mappings"] += 1
    return counts


def _proc_start_ticks(pid: int) -> int:
    raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    return int(raw.rsplit(")", 1)[1].split()[19])


def _snapshot(stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    facts = {
        "stage": stage,
        "utc": datetime.now(UTC).isoformat(),
        "monotonic_seconds": time.monotonic(),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "affinity_cpus": sorted(os.sched_getaffinity(0)),
        "current_rss_bytes": int(
            int(next(
                line.split()[1]
                for line in Path("/proc/self/status").read_text().splitlines()
                if line.startswith("VmRSS:")
            ))
            * 1024
        ),
        "current_swap_bytes": int(
            int(next(
                line.split()[1]
                for line in Path("/proc/self/status").read_text().splitlines()
                if line.startswith("VmSwap:")
            ))
            * 1024
        ),
        "process_peak_rss_bytes": int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        )
        * 1024,
        "host_memory": _read_meminfo(),
        "numa_maps_policy_counts": _numa_maps_summary(),
    }
    payload.setdefault("stages", []).append(facts)
    _write_receipt(payload)
    print(f"[{facts['utc']}] local QA stage: {stage}", flush=True)
    if facts["host_memory"].get("MemAvailable", 0) < HOST_AVAILABLE_FLOOR_BYTES:
        payload["status"] = "STOPPED_BELOW_HOST_AVAILABLE_FLOOR"
        payload["stop_reason"] = {
            "available_bytes": facts["host_memory"].get("MemAvailable"),
            "floor_bytes": HOST_AVAILABLE_FLOOR_BYTES,
            "detected_after_stage": stage,
        }
        _write_receipt(payload)
        raise SystemExit(73)
    return facts


def _write_receipt(payload: dict[str, Any]) -> None:
    target = Path(payload["receipt_path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_jsonable(payload), sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


def _error_facts(first: np.ndarray, second: np.ndarray) -> dict[str, Any]:
    left = np.asarray(first)
    right = np.asarray(second)
    if left.shape != right.shape:
        raise ValueError(f"comparison shapes differ: {left.shape} vs {right.shape}")
    difference = left - right
    if not (
        np.all(np.isfinite(left.real))
        and np.all(np.isfinite(left.imag))
        and np.all(np.isfinite(right.real))
        and np.all(np.isfinite(right.imag))
    ):
        raise FloatingPointError("local QA comparison contains non-finite values")
    first_norm = float(np.linalg.norm(left.ravel()))
    second_norm = float(np.linalg.norm(right.ravel()))
    scale = max(first_norm, second_norm, np.finfo(np.float64).tiny)
    return {
        "shape": [int(item) for item in left.shape],
        "max_abs_difference": float(np.max(np.abs(difference), initial=0.0)),
        "frobenius_difference": float(np.linalg.norm(difference.ravel())),
        "reference_scale_frobenius": scale,
        "relative_frobenius_difference": float(np.linalg.norm(difference.ravel()))
        / scale,
        "finite": True,
    }


def _stable_key_hash(keys: set[tuple[Any, ...]], *, oriented: bool) -> str:
    digest = hashlib.sha256()
    for key in sorted(keys):
        tag = int(key[0])
        digest.update(tag.to_bytes(4, "little", signed=True))
        coordinates = np.asarray(key[1:-1] if oriented else key[1:], dtype="<f8")
        digest.update(coordinates.tobytes(order="C"))
        if oriented:
            digest.update(int(key[-1]).to_bytes(4, "little", signed=False))
    return digest.hexdigest()


def _scaled_scalar_difference(first: float, second: float) -> float:
    left = float(first)
    right = float(second)
    scale = max(abs(left), abs(right), np.finfo(np.float64).tiny)
    return abs(left - right) / scale


def _local_condensed_state(
    tensor: np.ndarray,
    element: Any,
    cell_permutation: int,
    orient_cell_tensor,
    strict_local_lu,
) -> dict[str, Any]:
    from scipy.linalg import lu_solve

    oriented = np.asarray(tensor, dtype=np.complex128).copy()
    orient_cell_tensor(
        element,
        oriented,
        np.asarray([cell_permutation], dtype=np.uint32),
    )
    basix_element = element.basix_element
    dimension = int(element.space_dimension)
    interior = np.asarray(basix_element.entity_dofs[3][0], dtype=np.int32)
    trace = np.setdiff1d(np.arange(dimension, dtype=np.int32), interior)
    A_ii = oriented[np.ix_(interior, interior)]
    A_it = oriented[np.ix_(interior, trace)]
    A_ti = oriented[np.ix_(trace, interior)]
    A_tt = oriented[np.ix_(trace, trace)]
    interior_lu, identity_residual = strict_local_lu(A_ii)
    recovery = -lu_solve(interior_lu, A_it)
    adjoint_trace_solution = lu_solve(interior_lu, A_ti.conj().T, trans=2)
    rhs_trace = -adjoint_trace_solution.conj().T
    schur = A_tt + A_ti @ recovery
    values = {
        "raw_tensor": np.asarray(tensor, dtype=np.complex128),
        "oriented_tensor": oriented,
        "schur": schur,
        "recovery": recovery,
        "trace_from_interior_rhs": rhs_trace,
    }
    if any(
        not (np.all(np.isfinite(value.real)) and np.all(np.isfinite(value.imag)))
        for value in values.values()
    ):
        raise FloatingPointError("local tensor/Schur/recovery contains non-finite values")
    return {
        **values,
        "local_dofs": dimension,
        "trace_dofs": int(trace.size),
        "interior_dofs": int(interior.size),
        "local_lu_identity_relative_residual": float(identity_residual),
    }


def _state_comparisons(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    return {
        name: _error_facts(first[name], second[name])
        for name in (
            "raw_tensor",
            "oriented_tensor",
            "schur",
            "recovery",
            "trace_from_interior_rhs",
        )
    }


def _key_census(
    msh: Any,
    cell_tags: Any,
    cell_permutations: np.ndarray,
    *,
    canonical_swept_hex_coordinates,
) -> tuple[dict[str, Any], dict[tuple[Any, ...], list[int]], dict[int, int]]:
    tdim = msh.topology.dim
    cell_count = int(msh.topology.index_map(tdim).size_local)
    tags = np.full(cell_count, -1, dtype=np.int32)
    indices = np.asarray(cell_tags.indices, dtype=np.int32)
    values = np.asarray(cell_tags.values, dtype=np.int32)
    owned = (indices >= 0) & (indices < cell_count)
    tags[indices[owned]] = values[owned]
    if np.any(tags < 0):
        raise ValueError("cache census found an untagged owned cell")

    physical_raw_keys: set[tuple[Any, ...]] = set()
    translated_raw_keys: set[tuple[Any, ...]] = set()
    physical_schur_keys: set[tuple[Any, ...]] = set()
    translated_schur_keys: set[tuple[Any, ...]] = set()
    translated_schur_cells: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    class_slopes: dict[tuple[Any, ...], float] = {}
    class_centers: dict[int, np.ndarray] = {}
    orientation_counts = Counter(int(value) for value in cell_permutations)
    physical_classes_by_tag: Counter[int] = Counter()
    translated_classes_by_tag: Counter[int] = Counter()
    translated_schur_classes_by_tag: Counter[int] = Counter()
    all_slope_scores = np.empty(cell_count, dtype=np.float64)
    global_min_det_analytic = float("inf")
    global_max_det_sampled = float("-inf")
    translation_jacobian_relative_differences: dict[str, float] = {
        "min_detJ_sampled": 0.0,
        "max_detJ_sampled": 0.0,
        "min_detJ_analytic": 0.0,
    }

    for cell in range(cell_count):
        coordinates, physical_identity, facts = canonical_swept_hex_coordinates(
            msh,
            cell,
            tolerance=1.0e-11,
            translation_invariant_form=False,
        )
        translated_coordinates, translated_identity, translated_facts = (
            canonical_swept_hex_coordinates(
                msh,
                cell,
                tolerance=1.0e-11,
                translation_invariant_form=True,
            )
        )
        del coordinates, translated_coordinates
        tag = int(tags[cell])
        orientation = int(cell_permutations[cell])
        physical_raw = (tag, *physical_identity)
        translated_raw = (tag, *translated_identity)
        physical_schur = (*physical_raw, orientation)
        translated_schur = (*translated_raw, orientation)
        if physical_raw not in physical_raw_keys:
            physical_classes_by_tag[tag] += 1
        if translated_raw not in translated_raw_keys:
            translated_classes_by_tag[tag] += 1
        if translated_schur not in translated_schur_keys:
            translated_schur_classes_by_tag[tag] += 1
        physical_raw_keys.add(physical_raw)
        translated_raw_keys.add(translated_raw)
        physical_schur_keys.add(physical_schur)
        translated_schur_keys.add(translated_schur)
        translated_schur_cells[translated_schur].append(cell)
        x_ratio = facts["x_width_z1"] / facts["x_width_z0"]
        y_ratio = facts["y_width_z1"] / facts["y_width_z0"]
        slope = float(max(abs(x_ratio - 1.0), abs(y_ratio - 1.0)))
        all_slope_scores[cell] = slope
        class_slopes[translated_schur] = max(
            class_slopes.get(translated_schur, 0.0), slope
        )
        geometry = np.asarray(msh.geometry.x[msh.geometry.dofmap[cell]], dtype=np.float64)
        class_centers[cell] = geometry.mean(axis=0)
        global_min_det_analytic = min(
            global_min_det_analytic, facts["min_detJ_analytic"]
        )
        global_max_det_sampled = max(
            global_max_det_sampled, facts["max_detJ_sampled"]
        )
        for name, previous in translation_jacobian_relative_differences.items():
            translation_jacobian_relative_differences[name] = max(
                previous,
                _scaled_scalar_difference(facts[name], translated_facts[name]),
            )

    repeat_classes = {
        key: cells for key, cells in translated_schur_cells.items() if len(cells) >= 2
    }
    if not repeat_classes:
        raise RuntimeError("no repeated exact same-material/orientation cache class exists")
    selected_class = max(
        repeat_classes,
        key=lambda key: (class_slopes[key], len(repeat_classes[key]), key),
    )
    class_cells = repeat_classes[selected_class]
    pair = max(
        (
            (left, right)
            for i, left in enumerate(class_cells)
            for right in class_cells[i + 1 :]
        ),
        key=lambda values: float(
            np.linalg.norm(class_centers[values[0]] - class_centers[values[1]])
        ),
    )
    worst_cell = int(np.argmax(all_slope_scores))
    facts_out = {
        "owned_cell_count": cell_count,
        "orientation_histogram_actual": {
            str(key): int(count) for key, count in sorted(orientation_counts.items())
        },
        "actual_key_schema": {
            "raw_tensor": "('actual_space', material_tag, exact_float64_8x3_canonical_vertices)",
            "canonical_coordinates": "physical coordinates by default; subtract cell minimum only when explicit mapped_geometry_translation_invariant=true",
            "schur_lu_recovery": "raw tensor key plus exact cell orientation info",
            "rounding": "none",
            "material_tag_is_key_component": True,
            "orientation_is_separate_schur_key_component": True,
        },
        "physical_coordinates": {
            "unique_raw_tensor_classes": len(physical_raw_keys),
            "unique_oriented_schur_classes": len(physical_schur_keys),
            "raw_classes_by_tag": {
                str(key): int(value)
                for key, value in sorted(physical_classes_by_tag.items())
            },
            "raw_tensor_numeric_payload_bytes_at_882_dofs": int(
                len(physical_raw_keys) * 882 * 882 * np.dtype(np.complex128).itemsize
            ),
            "estimated_retained_numeric_payload_bytes_excluding_python_overhead": int(
                len(physical_raw_keys) * 882 * 882 * np.dtype(np.complex128).itemsize
                + len(physical_schur_keys)
                * (
                    432 * 432
                    + 450 * 432
                    + 450 * 450
                    + 432 * 450
                )
                * np.dtype(np.complex128).itemsize
                + 450 * 450 * np.dtype(np.float64).itemsize
            ),
            "key_sha256": _stable_key_hash(physical_raw_keys, oriented=False),
        },
        "translation_normalized_candidate": {
            "unique_raw_tensor_classes": len(translated_raw_keys),
            "unique_oriented_schur_classes": len(translated_schur_keys),
            "raw_classes_by_tag": {
                str(key): int(value)
                for key, value in sorted(translated_classes_by_tag.items())
            },
            "oriented_schur_classes_by_tag": {
                str(key): int(value)
                for key, value in sorted(translated_schur_classes_by_tag.items())
            },
            "raw_tensor_numeric_payload_bytes_at_882_dofs": int(
                len(translated_raw_keys)
                * 882
                * 882
                * np.dtype(np.complex128).itemsize
            ),
            "estimated_retained_numeric_payload_bytes_excluding_python_overhead": int(
                len(translated_raw_keys)
                * 882
                * 882
                * np.dtype(np.complex128).itemsize
                + len(translated_schur_keys)
                * (
                    432 * 432
                    + 450 * 432
                    + 450 * 450
                    + 432 * 450
                )
                * np.dtype(np.complex128).itemsize
                + 450 * 450 * np.dtype(np.float64).itemsize
            ),
            "raw_key_sha256": _stable_key_hash(translated_raw_keys, oriented=False),
            "oriented_schur_key_sha256": _stable_key_hash(
                translated_schur_keys, oriented=True
            ),
        },
        "analytic_jacobian_extrema_nm3": {
            "global_minimum_analytic": global_min_det_analytic,
            "global_maximum_sampled": global_max_det_sampled,
            "all_cells_passed_production_exact_mapped_q1_check": True,
            "physical_vs_translation_normalized_max_scaled_determinant_difference": (
                translation_jacobian_relative_differences
            ),
        },
        "maximum_relative_x_or_y_taper": float(np.max(all_slope_scores)),
        "selected_repeated_worst_slope_class": {
            "material_tag": int(selected_class[0]),
            "orientation": int(selected_class[-1]),
            "cell_count_in_full_mesh": len(class_cells),
            "slope_score": class_slopes[selected_class],
            "representative_pair_parent_cell_indices": [int(pair[0]), int(pair[1])],
            "representative_pair_translation_distance_nm": float(
                np.linalg.norm(class_centers[pair[0]] - class_centers[pair[1]])
            ),
        },
        "single_worst_slope_parent_cell": {
            "cell_index": worst_cell,
            "slope_score": float(all_slope_scores[worst_cell]),
            "tag": int(tags[worst_cell]),
            "orientation": int(cell_permutations[worst_cell]),
        },
        "representative_cells_parent_indices": sorted({int(pair[0]), int(pair[1]), worst_cell}),
    }
    return facts_out, translated_schur_cells, tags


def _compile_volume_operator(
    msh: Any,
    cell_tags: Any,
    cfg: Any,
    function_space: Any,
    quadrature_degree: int,
    *,
    fem: Any,
    ufl: Any,
    PETSc: Any,
    build_physical_volume_terms,
) -> Any:
    trial = ufl.TrialFunction(function_space)
    test = ufl.TestFunction(function_space)
    dx = ufl.Measure(
        "dx",
        domain=msh,
        subdomain_data=cell_tags,
        metadata={
            "quadrature_degree": int(quadrature_degree),
            "quadrature_rule": "default",
        },
    )
    curl_form, mass_form = build_physical_volume_terms(cfg, trial, test, dx)
    return fem.form(curl_form + mass_form, dtype=PETSc.ScalarType)


def run(
    receipt_path: Path,
    *,
    supervisor_cpu: int,
    worker_cpu: int,
    supervisor_pid: int,
    supervisor_start_ticks: int,
) -> dict[str, Any]:
    global _ACTIVE_PAYLOAD
    tracked_diff = subprocess.run(
        ["git", "diff", "HEAD", "--binary"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    bound_paths = (
        "src/common/config_3d.py",
        "src/common/materials.py",
        "src/geometry/mesh_builder_3d.py",
        "src/geometry/task40_gate_cd_mesh_plan.py",
        "src/io/input_validation.py",
        "src/io/native_capacity_profile.py",
        "src/solvers/common_3d_forms.py",
        "src/solvers/fullspace_physical_intermediate_runtime.py",
        "src/solvers/hcurl_assembly_time_condensation.py",
        "scripts/activate_task40_phi90_pord64.sh",
        "scripts/qa_task40_gate_cd_local_cache_quadrature.py",
    )
    payload: dict[str, Any] = {
        "schema": "task40.gate-cd-local-cell-cache-quadrature-qa.v1",
        "status": "RUNNING",
        "receipt_path": str(receipt_path.resolve()),
        "scope": {
            "actual_mesh": "rebuild only the authorized 27,600-cell mapped mesh",
            "cache_identity": "production exact mapped-hex cell-key census; no tensor array retained for the full mesh",
            "quadrature": "actual p6 local volume curl+complex-mass element tensors at q15/q21/q27 on selected real-cell submesh",
            "translation_invariance": "physical-coordinate versus explicitly translation-normalized local tensor, orientation, Schur and recovery",
            "local_matrix_size": "at most three actual cells; four tensor variants per selected cell may be retained for physical/q15/q21/q27 comparison; local 450x450 interior LU only",
            "global_matrix_factor_solve": "NOT_BUILT_NOT_CALLED",
            "visualization_pss_uss_smaps": "NOT_WRITTEN_NOT_READ",
        },
        "input_sha256": _sha256_file(INPUT),
        "source_identity": {
            "git_head": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "tracked_diff_from_head_sha256": hashlib.sha256(tracked_diff).hexdigest(),
            "worktree_file_sha256_by_path": {
                relative: _sha256_file(ROOT / relative)
                for relative in bound_paths
            },
            "script_sha256": _sha256_file(Path(__file__).resolve()),
        },
        "resource_contract": {
            "minimum_available_bytes": HOST_AVAILABLE_FLOOR_BYTES,
            "fixed_rss_cap_bytes": None,
            "swap_policy": "observe_only",
            "pss_uss": "disabled",
            "supervisor_cpu_from_fresh": supervisor_cpu,
            "worker_cpu_from_fresh": worker_cpu,
            "numa_expected": "interleave:0-1",
        },
        "supervisor_anchor": {
            "pid": supervisor_pid,
            "start_ticks_from_fresh": supervisor_start_ticks,
        },
        "stages": [],
    }
    _ACTIVE_PAYLOAD = payload
    _write_receipt(payload)
    _snapshot("qa_process_started", payload)

    if os.environ.get("HWLOC_COMPONENTS") != "-x86":
        raise RuntimeError("bounded host QA requires process-local HWLOC_COMPONENTS=-x86")
    if os.environ.get("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("Task40 qualified activation is not active")
    if os.environ.get("TASK39EXTRA_PORD64_ACTIVATION") != "1":
        raise RuntimeError("qualified PORD64 activation is not active")
    if sorted(os.sched_getaffinity(0)) != [worker_cpu]:
        raise RuntimeError("worker affinity differs from its fresh-selected singleton CPU")
    if _proc_start_ticks(supervisor_pid) != supervisor_start_ticks:
        raise RuntimeError("fresh-selected supervisor PID start_ticks changed")
    if sorted(os.sched_getaffinity(supervisor_pid)) != [supervisor_cpu]:
        raise RuntimeError("supervisor anchor affinity differs from fresh-selected CPU")
    if Path(f"/proc/{supervisor_pid}/comm").read_text().strip() not in {
        "python", "python3"
    }:
        raise RuntimeError("fresh-selected supervisor PID is not the dedicated watchdog Python")
    for variable in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        if os.environ.get(variable) != "1":
            raise RuntimeError(f"{variable} must be 1")

    import basix
    import dolfinx
    import dolfinx_mpc
    import mpi4py
    import petsc4py
    import ufl
    from basix.ufl import element
    from dolfinx import default_real_type, fem, mesh
    from mpi4py import MPI
    from petsc4py import PETSc

    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.geometry.task40_gate_cd_mesh_plan import (
        GATE_CD_STATIC_PLAN,
        gate_cd_live_mesh_facts,
    )
    from src.io.input_validation import (
        load_and_resolve,
        simulation_config_3d_from_normalized,
    )
    from src.io.resolved_config import resolved_config_sha256
    from src.solvers.common_3d_forms import _build_physical_volume_terms
    from src.solvers.fullspace_physical_intermediate_runtime import (
        fine_volume_quadrature_metadata,
    )
    from src.solvers.hcurl_assembly_time_condensation import (
        _canonical_swept_hex_coordinates,
        _cell_integral_kernels,
        _orient_cell_tensor,
        _strict_local_lu,
        _tabulate_raw_tensor_class,
        build_unconstrained_assembly_time_condensation,
    )

    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError(f"bounded QA requires MPI1, got {MPI.COMM_WORLD.size}")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("qualified PETSc must use complex128")
    if np.dtype(PETSc.IntType) != np.dtype(np.int64):
        raise RuntimeError("qualified PETSc must use 64-bit indices")
    if np.dtype(default_real_type) != np.dtype(np.float64):
        raise RuntimeError("qualified DOLFINx geometry must be float64")
    expected_petsc_root = (Path(os.environ["TASK39EXTRA_PORD64_ROOT"]) / "petsc").resolve()
    mapped_libs = sorted(
        {
            Path(line.split()[-1]).resolve().as_posix()
            for line in Path("/proc/self/maps").read_text().splitlines()
            if "libpetsc.so" in line and line.split()[-1].startswith("/")
        }
    )
    if not mapped_libs or any(
        not Path(item).is_relative_to(expected_petsc_root) for item in mapped_libs
    ):
        raise RuntimeError("live mapped libpetsc does not come from qualified PORD64")
    payload["abi"] = {
        "python": sys.executable,
        "petsc_version": list(PETSc.Sys.getVersion()),
        "petsc_scalar": str(np.dtype(PETSc.ScalarType)),
        "petsc_integer": str(np.dtype(PETSc.IntType)),
        "petsc_mapped_library_paths": mapped_libs,
        "dolfinx_version": str(dolfinx.__version__),
        "dolfinx_module": str(Path(dolfinx.__file__).resolve()),
        "basix_version": str(basix.__version__),
        "dolfinx_mpc_module": str(Path(dolfinx_mpc.__file__).resolve()),
        "mpi4py_module": str(Path(mpi4py.__file__).resolve()),
        "petsc4py_module": str(Path(petsc4py.__file__).resolve()),
    }
    _snapshot("qualified_abi_verified", payload)

    specification = load_and_resolve(INPUT)
    if specification.identity["run_id"] != "task40_gate_cd_0p7_mapped_p6_staged_v1":
        raise RuntimeError("gate_cd staged QA identity changed")
    if specification.solver["native_capacity_profile"] != EXPECTED_PROFILE:
        raise RuntimeError("gate_cd staged QA resolved to another profile")
    resolved = specification.as_jsonable()
    cfg = simulation_config_3d_from_normalized(resolved)
    if cfg.mesh_plan_sha256 != GATE_CD_STATIC_PLAN.plan_sha256:
        raise RuntimeError("gate_cd plan SHA differs from the frozen static plan")
    payload["resolved_identity"] = {
        "model_id": specification.identity["model_id"],
        "run_id": specification.identity["run_id"],
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "resolved_config_sha256": resolved_config_sha256(specification),
        "mesh_plan_id": cfg.mesh_plan_id,
        "mesh_plan_sha256": cfg.mesh_plan_sha256,
        "output_parent": str(specification.expected_output_parent),
    }
    _snapshot("production_loader_identity_verified", payload)

    scratch = Path(receipt_path).resolve().parent / "mesh_builder_scratch"
    mesh_data = build_airbox_mesh_3d(cfg, scratch)
    live_mesh = gate_cd_live_mesh_facts(
        mesh_data.mesh, mesh_data.cell_tags, GATE_CD_STATIC_PLAN
    )
    if live_mesh.get("status") != "PASS":
        raise RuntimeError("actual mapped mesh QA did not pass")
    msh = mesh_data.mesh
    V = fem.functionspace(
        msh,
        element("N1curl", msh.basix_cell(), 6, dtype=default_real_type),
    )
    msh.topology.create_entity_permutations()
    cell_permutations = np.asarray(msh.topology.get_cell_permutation_info())
    element_basix = V.element.basix_element
    if int(element_basix.degree) != 6 or str(element_basix.lagrange_variant.name) != "legendre":
        raise RuntimeError("actual mapped mesh did not build the p6 N1E Legendre space")
    payload["actual_mesh_space"] = {
        "live_mesh": live_mesh,
        "global_p6_dofs": int(V.dofmap.index_map.size_global),
        "local_p6_dofs": int(V.dofmap.index_map.size_local),
        "p6_local_dimension": int(element_basix.dim),
        "cell_permutation_info_sha256": hashlib.sha256(
            np.ascontiguousarray(cell_permutations).view(np.uint8).tobytes()
        ).hexdigest(),
    }
    _snapshot("actual_mesh_and_p6_space_built", payload)

    census, _classes, parent_tags = _key_census(
        msh,
        mesh_data.cell_tags,
        cell_permutations,
        canonical_swept_hex_coordinates=_canonical_swept_hex_coordinates,
    )
    payload["cell_condensation_key_census"] = census
    _snapshot("exact_full_mesh_cache_key_census_complete", payload)

    pair = census["selected_repeated_worst_slope_class"][
        "representative_pair_parent_cell_indices"
    ]
    worst = census["single_worst_slope_parent_cell"]["cell_index"]
    selected_parent_cells = sorted({int(pair[0]), int(pair[1]), int(worst)})
    submesh, submesh_to_parent, _vertex_map, _geometry_map = mesh.create_submesh(
        msh, msh.topology.dim, np.asarray(selected_parent_cells, dtype=np.int32)
    )
    submesh_cell_count = int(
        submesh.topology.index_map(msh.topology.dim).size_local
    )
    submesh_parent_cells = np.asarray(
        submesh_to_parent.sub_topology_to_topology(
            np.arange(submesh_cell_count, dtype=np.int32),
            inverse=False,
        ),
        dtype=np.int32,
    )
    if submesh_parent_cells.shape != (len(selected_parent_cells),):
        raise RuntimeError("selected local submesh does not map all requested parent cells")
    if (
        np.any(submesh_parent_cells < 0)
        or len(np.unique(submesh_parent_cells)) != len(selected_parent_cells)
        or set(map(int, submesh_parent_cells)) != set(selected_parent_cells)
    ):
        raise RuntimeError("DOLFINx EntityMap did not preserve exact selected parent cells")
    submesh_tag_values = parent_tags[submesh_parent_cells]
    submesh_cell_tags = mesh.meshtags(
        submesh,
        submesh.topology.dim,
        np.arange(len(submesh_parent_cells), dtype=np.int32),
        np.asarray(submesh_tag_values, dtype=np.int32),
    )
    Vsub = fem.functionspace(
        submesh,
        element("N1curl", submesh.basix_cell(), 6, dtype=default_real_type),
    )
    submesh.topology.create_entity_permutations()
    submesh_permutations = np.asarray(submesh.topology.get_cell_permutation_info())
    parent_to_local = {
        int(parent): local for local, parent in enumerate(submesh_parent_cells)
    }
    pair_local = [parent_to_local[int(value)] for value in pair]
    if (
        submesh_tag_values[pair_local[0]] != submesh_tag_values[pair_local[1]]
        or submesh_permutations[pair_local[0]] != submesh_permutations[pair_local[1]]
    ):
        raise RuntimeError("selected repeated class lost same material/orientation on submesh")
    payload["local_cell_witness"] = {
        "parent_cell_indices": selected_parent_cells,
        "submesh_to_parent_cell_indices": submesh_parent_cells.tolist(),
        "selected_pair_local_indices": pair_local,
        "selected_pair_tag": int(submesh_tag_values[pair_local[0]]),
        "selected_pair_orientation": int(submesh_permutations[pair_local[0]]),
        "selected_pair_cache_key_sha256": hashlib.sha256(
            repr(
                (
                    int(submesh_tag_values[pair_local[0]]),
                    tuple(
                        _canonical_swept_hex_coordinates(
                            submesh,
                            pair_local[0],
                            tolerance=1.0e-11,
                            translation_invariant_form=True,
                        )[1]
                    ),
                    int(submesh_permutations[pair_local[0]]),
                )
            ).encode()
        ).hexdigest(),
    }
    _snapshot("selected_actual_worst_slope_translated_cell_pair", payload)

    metadata_setup = {
        "spaces": {6: V},
        "mesh": msh,
        "mesh_data": mesh_data,
        # The metadata helper only reads the function space from this carrier;
        # no MPC build or solver state is created in this QA.
        "floquets": {6: type("FloquetCarrier", (), {"mpc": type("MpcSpaceCarrier", (), {"function_space": V})()})()},
    }
    volume_metadata, volume_records = fine_volume_quadrature_metadata(metadata_setup, cfg)
    expected_q15 = (
        {"quadrature_degree": 15, "quadrature_rule": "default"},
        {"quadrature_degree": 15, "quadrature_rule": "default"},
    )
    if tuple(volume_metadata) != expected_q15:
        raise RuntimeError(f"production FFCx volume analysis changed from q15/default: {volume_metadata!r}")
    payload["production_volume_quadrature"] = {
        "metadata": volume_metadata,
        "records": volume_records,
        "analysis_source": "fine_volume_quadrature_metadata on actual gate_cd P6 mesh/space; FFCx analysis only",
        "compiled_or_assembled": False,
    }
    _snapshot("actual_ffcx_volume_metadata_confirmed_q15_default", payload)

    q_states: dict[int, dict[int, dict[str, Any]]] = {}
    q15_physical_states: dict[int, dict[str, Any]] = {}
    q_forms: dict[int, Any] = {}
    submesh_tags = submesh_cell_tags
    for quadrature_degree in QUADRATURE_DEGREES:
        compiled = _compile_volume_operator(
            submesh,
            submesh_tags,
            cfg,
            Vsub,
            quadrature_degree,
            fem=fem,
            ufl=ufl,
            PETSc=PETSc,
            build_physical_volume_terms=_build_physical_volume_terms,
        )
        q_forms[quadrature_degree] = compiled
        kernels = _cell_integral_kernels(
            compiled,
            sum_duplicate_cell_integrals=True,
        )
        dimension = int(Vsub.element.space_dimension)
        current: dict[int, dict[str, Any]] = {}
        for subcell in range(len(submesh_parent_cells)):
            tag = int(submesh_tag_values[subcell])
            physical_coordinates, _physical_identity, physical_facts = (
                _canonical_swept_hex_coordinates(
                    submesh,
                    subcell,
                    tolerance=1.0e-11,
                    translation_invariant_form=False,
                )
            )
            normalized_coordinates, _normalized_identity, normalized_facts = (
                _canonical_swept_hex_coordinates(
                    submesh,
                    subcell,
                    tolerance=1.0e-11,
                    translation_invariant_form=True,
                )
            )
            physical_tensor = _tabulate_raw_tensor_class(
                compiled,
                kernels,
                physical_coordinates,
                tag=tag,
                dimension=dimension,
            )
            normalized_tensor = _tabulate_raw_tensor_class(
                compiled,
                kernels,
                normalized_coordinates,
                tag=tag,
                dimension=dimension,
            )
            permutation = int(submesh_permutations[subcell])
            physical_state = _local_condensed_state(
                physical_tensor,
                Vsub.element,
                permutation,
                _orient_cell_tensor,
                _strict_local_lu,
            )
            normalized_state = _local_condensed_state(
                normalized_tensor,
                Vsub.element,
                permutation,
                _orient_cell_tensor,
                _strict_local_lu,
            )
            jacobian_differences = {
                name: _scaled_scalar_difference(
                    physical_facts[name], normalized_facts[name]
                )
                for name in (
                    "min_detJ_sampled",
                    "max_detJ_sampled",
                    "min_detJ_analytic",
                )
            }
            if quadrature_degree == 15:
                q15_physical_states[subcell] = physical_state
            current[subcell] = normalized_state
            payload.setdefault("selected_cell_jacobian_translation_differences", {})[
                str(int(submesh_parent_cells[subcell]))
            ] = jacobian_differences
        q_states[quadrature_degree] = current
        payload.setdefault("local_quadrature_forms", {})[str(quadrature_degree)] = {
            "form_integral_kernel_ids": [int(value) for value in sorted(kernels)],
            "cell_integral_kernel_count": int(
                sum(len(value) if isinstance(value, (tuple, list)) else 1 for value in kernels.values())
            ),
            "metadata": {"quadrature_degree": quadrature_degree, "quadrature_rule": "default"},
            "compiled_only_for_selected_2_or_3_cell_submesh": True,
            "global_matrix_or_factor": False,
        }
        if quadrature_degree == 15:
            payload["local_quadrature_forms"][str(quadrature_degree)]["local_tensor_identity"] = {
                str(subcell): {
                    "raw_tensor_physical_coordinates_sha256": hashlib.sha256(
                        np.ascontiguousarray(q15_physical_states[subcell]["raw_tensor"]).view(np.uint8).tobytes()
                    ).hexdigest(),
                    "raw_tensor_translation_normalized_sha256": hashlib.sha256(
                        np.ascontiguousarray(current[subcell]["raw_tensor"]).view(np.uint8).tobytes()
                    ).hexdigest(),
                }
                for subcell in current
            }
        _snapshot(f"actual_p6_local_cell_q{quadrature_degree}_compiled_and_tabulated", payload)

    local_quadrature_comparisons = {}
    for subcell in range(len(submesh_parent_cells)):
        local_quadrature_comparisons[str(int(submesh_parent_cells[subcell]))] = {
            f"q{left}_vs_q{right}": _state_comparisons(q_states[left][subcell], q_states[right][subcell])
            for left, right in ((15, 21), (15, 27), (21, 27))
        }
    translation_local_comparisons = {}
    for subcell in range(len(submesh_parent_cells)):
        translation_local_comparisons[str(int(submesh_parent_cells[subcell]))] = _state_comparisons(
            q15_physical_states[subcell], q_states[15][subcell]
        )
    pair_local_comparison = {
        "physical_coordinates": _state_comparisons(
            q15_physical_states[pair_local[0]], q15_physical_states[pair_local[1]]
        ),
        "translation_normalized": _state_comparisons(
            q_states[15][pair_local[0]], q_states[15][pair_local[1]]
        ),
    }
    payload["local_q15_q21_q27_comparison"] = {
        "local_quadrature_degree_is_polynomial_degree_not_points_per_axis": True,
        "reference_is_highest_tested_q27_not_exact_truth": True,
        "per_cell_q_comparisons": local_quadrature_comparisons,
        "physical_vs_translation_normalized_per_cell_q15": translation_local_comparisons,
        "translated_same_shape_material_orientation_pair_q15": pair_local_comparison,
        "threshold": "diagnostic only; no new production quadrature gate is introduced",
    }
    payload["retained_local_array_storage"] = {
        "scope": "selected actual cells only; raw/oriented tensors and local condensed blocks are retained solely for the required physical/q15/q21/q27 comparisons",
        "array_bytes": int(
            sum(
                int(value.nbytes)
                for states in (q_states, {15: q15_physical_states})
                for per_cell in states.values()
                for state in per_cell.values()
                for value in state.values()
                if isinstance(value, np.ndarray)
            )
        ),
        "selected_cell_count": len(submesh_parent_cells),
    }
    _snapshot("actual_p6_q15_q21_q27_local_tensor_schur_recovery_comparisons_complete", payload)

    cache_path_comparisons = {}
    for translation_invariant in (False, True):
        system = build_unconstrained_assembly_time_condensation(
            q_forms[15],
            Vsub,
            submesh_cell_tags,
            mpc=None,
            appended_global_rows=0,
            strict_local_checks=True,
            retain_local_schur_for_matrix_free=True,
            materialize_global_matrix=False,
            geometry_identity_policy="mapped_exact",
            mapped_geometry_translation_invariant=translation_invariant,
            share_identity_cache=True,
            sum_duplicate_cell_integrals=True,
        )
        if system.matrix is not None:
            raise RuntimeError("local cache test unexpectedly created a PETSc matrix")
        audit = system.build_audit
        class_keys_by_subcell = [item.class_key for item in system.cell_recovery_maps]
        pair_keys = [class_keys_by_subcell[index] for index in pair_local]
        if translation_invariant and pair_keys[0] != pair_keys[1]:
            raise RuntimeError("translation-normalized production Schur/recovery keys did not merge")
        if not translation_invariant and pair_keys[0] == pair_keys[1]:
            raise RuntimeError("physical-coordinate production cache unexpectedly merged translated cells")
        if not translation_invariant:
            expected_schur = system.retained_local_schur_by_class
            expected_recovery = system.interior_from_trace_by_class
            for pair_index in pair_local:
                key = class_keys_by_subcell[pair_index]
                direct = q15_physical_states[pair_index]
                cache_path_comparisons.setdefault("physical_cells_vs_production_cache", {})[
                    str(int(submesh_parent_cells[pair_index]))
                ] = {
                    "schur": _error_facts(expected_schur[key], direct["schur"]),
                    "recovery": _error_facts(expected_recovery[key], direct["recovery"]),
                }
        else:
            key = pair_keys[0]
            expected_schur = system.retained_local_schur_by_class[key]
            expected_recovery = system.interior_from_trace_by_class[key]
            for pair_index in pair_local:
                direct = q_states[15][pair_index]
                cache_path_comparisons.setdefault("normalized_cells_vs_shared_production_cache", {})[
                    str(int(submesh_parent_cells[pair_index]))
                ] = {
                    "schur": _error_facts(expected_schur, direct["schur"]),
                    "recovery": _error_facts(expected_recovery, direct["recovery"]),
                }
        cache_path_comparisons[
            "translation_normalized" if translation_invariant else "physical_coordinates"
        ] = {
            "mapped_geometry_translation_invariant": translation_invariant,
            "materialized_global_matrix": bool(audit["matrix_materialized"]),
            "global_rows": int(audit["matrix_rows"]),
            "raw_tensor_class_count_global_unique": int(audit["raw_tensor_class_count_global_unique"]),
            "oriented_schur_class_count_sum": int(audit["oriented_schur_class_count_sum"]),
            "retained_local_schur_class_count_local": int(audit["retained_local_schur_class_count_local"]),
            "cell_recovery_class_keys": [hashlib.sha256(repr(key).encode()).hexdigest() for key in class_keys_by_subcell],
            "mapped_hex_translation_removed": bool(audit["mapped_hex_translation_removed"]),
            "local_lu_identity_relative_residual_max": float(audit["local_lu_identity_relative_residual_max"]),
            "one_shared_cache_key_for_translated_pair": pair_keys[0] == pair_keys[1],
            "global_matrix_factor_solve": "NOT_BUILT_NOT_CALLED",
        }
        del system
        gc.collect()
    payload["production_local_cache_path_comparison"] = cache_path_comparisons
    _snapshot("production_local_tensor_schur_recovery_cache_paths_compared", payload)

    payload["status"] = "PASS_BOUNDED_GATE_CD_ACTUAL_CACHE_AND_LOCAL_QUADRATURE_QA"
    payload["completion"] = {
        "global_variational_matrix": False,
        "global_factor": False,
        "solve": False,
        "local_submesh_cells": len(submesh_parent_cells),
        "local_p6_tensors_tabulated": True,
        "local_interior_lu_scope": "strict per-cell 450x450 blocks only",
        "full_mesh_tensor_arrays_retained": False,
        "full_mesh_cache_identity_count_is_metadata_only": True,
        "task40_production_source_modified_by_qa": False,
    }
    _snapshot("local_cache_and_quadrature_qa_complete", payload)
    if payload["stages"][-1]["numa_maps_policy_counts"]["interleave_0_1_mappings"] <= 0:
        raise RuntimeError("worker lacks observed interleave:0-1 numa_maps mappings")
    del q_states, q15_physical_states, q_forms, Vsub, V, mesh_data, cfg, specification
    gc.collect()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--supervisor-cpu", type=int, required=True)
    parser.add_argument("--worker-cpu", type=int, required=True)
    parser.add_argument("--supervisor-pid", type=int, required=True)
    parser.add_argument("--supervisor-start-ticks", type=int, required=True)
    args = parser.parse_args()
    receipt = args.receipt.resolve()
    try:
        run(
            receipt,
            supervisor_cpu=args.supervisor_cpu,
            worker_cpu=args.worker_cpu,
            supervisor_pid=args.supervisor_pid,
            supervisor_start_ticks=args.supervisor_start_ticks,
        )
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1
    except BaseException as exc:
        payload = _ACTIVE_PAYLOAD or {
            "schema": "task40.gate-cd-local-cell-cache-quadrature-qa.v1",
            "receipt_path": str(receipt),
            "stages": [],
        }
        payload["status"] = "FAILED_LOCAL_QA_STAGE"
        payload["error"] = {"type": type(exc).__name__, "message": str(exc)}
        payload["traceback"] = traceback.format_exc()
        _write_receipt(payload)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
