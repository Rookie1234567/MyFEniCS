"""Narrow H1R.1 single-cell action diagnostics.

The runner intentionally constructs one affine hexahedron on ``COMM_SELF``.
It separates the existing dense-cell path (A), an exact-class diagnostic dense
cache (B), and a rank-one UFL direct action (C).  It is not a solver or a
production action backend.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from statistics import median
import sys
import time
from typing import Any

import numpy as np

from benchmarks.task033_case090_pde_core import attach_evidence_sha256
from benchmarks.run_task037_extra_candidate_h import _inspect_candidate_source


REPEATS = 4
H1R_DEGREES = (2, 3, 4, 6)
H1R_PAYLOAD_LIMIT_BYTES = 16 * 1024**2
H1R_DIRECT_BACKEND_IDENTITY = (
    "dolfinx.fem.assemble_vector(existing ndarray, rank-one form)"
)
P6_DENSE_CLASS_BYTES = 882**2 * np.dtype(np.complex128).itemsize
MATERIAL_COEFFICIENTS = {
    1: {
        "curl": complex(1.0 + 0.15j),
        "mass": complex(2.5 - 0.20j),
    },
    2: {
        "curl": complex(1.7 - 0.25j),
        "mass": complex(0.65 + 0.40j),
    },
}


@dataclass
class _CellContext:
    mesh: Any
    cell_tags: Any
    function_space: Any
    form_ufl: Any
    compiled_form: Any
    element: Any
    coordinates: np.ndarray
    widths: tuple[float, float, float]
    cell_info: np.ndarray
    cell_tag: int
    local_input: np.ndarray
    class_identity: dict[str, Any]


def _build_single_cell(degree: int) -> _CellContext:
    from basix.ufl import element
    from dolfinx import default_real_type, fem, mesh
    from mpi4py import MPI
    from petsc4py import PETSc
    import ufl

    from src.solvers.hcurl_assembly_time_condensation import (
        _canonical_axis_aligned_coordinates,
    )

    degree = int(degree)
    mesh_3d = mesh.create_unit_cube(
        MPI.COMM_SELF,
        1,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    cell_tags = mesh.meshtags(
        mesh_3d,
        mesh_3d.topology.dim,
        np.asarray([0], dtype=np.int32),
        np.asarray([1], dtype=np.int32),
    )
    function_space = fem.functionspace(
        mesh_3d,
        element(
            "N1curl",
            mesh_3d.basix_cell(),
            degree,
            dtype=default_real_type,
        ),
    )
    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    dx = ufl.Measure("dx", domain=mesh_3d, subdomain_data=cell_tags)
    terms = []
    for tag, coefficients in MATERIAL_COEFFICIENTS.items():
        terms.append(
            (
                PETSc.ScalarType(coefficients["curl"])
                * ufl.inner(ufl.curl(u), ufl.curl(v))
                + PETSc.ScalarType(coefficients["mass"])
                * ufl.inner(u, v)
            )
            * dx(tag)
        )
    form_ufl = sum(terms)
    compiled_form = fem.form(form_ufl)

    mesh_3d.topology.create_entity_permutations()
    cell_info = np.asarray(
        [mesh_3d.topology.get_cell_permutation_info()[0]], dtype=np.uint32
    )
    coordinates, widths = _canonical_axis_aligned_coordinates(
        mesh_3d,
        0,
        tolerance=1.0e-12,
    )
    coordinates = np.ascontiguousarray(coordinates, dtype=np.float64)
    coordinates.flags.writeable = False
    cell_info.flags.writeable = False
    nloc = int(function_space.element.space_dimension)
    local_input = (
        0.75
        + 0.017 * np.arange(nloc, dtype=np.float64)
        + 1j * (0.20 - 0.009 * np.arange(nloc, dtype=np.float64))
    ).astype(np.complex128)
    basix_element = function_space.element.basix_element
    class_identity = {
        "degree": degree,
        "element": {
            "basix_hash": int(basix_element.hash()),
            "basix_family": basix_element.family.name,
            "basix_map_type": basix_element.map_type.name,
            "basix_cell_type": basix_element.cell_type.name,
            "basix_degree": int(basix_element.degree),
        },
        "canonical_widths": [float(value) for value in widths],
        "canonical_coordinates": coordinates.tolist(),
        "material_coefficients": {
            str(tag): {
                name: [float(value.real), float(value.imag)]
                for name, value in coefficients.items()
            }
            for tag, coefficients in MATERIAL_COEFFICIENTS.items()
        },
        "cell_tag": 1,
        "cell_info": int(cell_info[0]),
    }
    class_identity["sha256"] = hashlib.sha256(
        json.dumps(class_identity, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return _CellContext(
        mesh=mesh_3d,
        cell_tags=cell_tags,
        function_space=function_space,
        form_ufl=form_ufl,
        compiled_form=compiled_form,
        element=function_space.element,
        coordinates=coordinates,
        widths=tuple(float(value) for value in widths),
        cell_info=cell_info,
        cell_tag=1,
        local_input=local_input,
        class_identity=class_identity,
    )


class _DenseCellPath:
    def __init__(self, context: _CellContext, *, retabulate: bool):
        from src.solvers.hcurl_assembly_time_condensation import (
            _cell_integral_kernels,
        )

        self.context = context
        self.retabulate = bool(retabulate)
        self.kernels = _cell_integral_kernels(context.compiled_form)
        dimension = int(context.element.space_dimension)
        started = time.perf_counter()
        self.tensor = np.empty((dimension, dimension), dtype=np.complex128)
        self.setup_seconds = float(time.perf_counter() - started)
        self.tabulation_count = 0
        self.orientation_count = 0
        self.gemv_count = 0
        self.last_tabulation_seconds = 0.0
        self.last_orientation_seconds = 0.0
        self.setup_tabulation_seconds = 0.0
        self.setup_orientation_seconds = 0.0

    def _tabulate_and_orient(self) -> None:
        from src.solvers.hcurl_assembly_time_condensation import (
            _orient_cell_tensor,
        )

        tensor = self.tensor
        tabulation_started = time.perf_counter()
        tensor.fill(0.0)
        ffi = self.context.compiled_form.module.ffi
        for kernel_id in (-1, self.context.cell_tag):
            kernel = self.kernels.get(kernel_id)
            if kernel is None:
                continue
            kernel(
                ffi.cast("double _Complex *", ffi.from_buffer(tensor)),
                ffi.NULL,
                ffi.NULL,
                ffi.cast(
                    "double *", ffi.from_buffer(self.context.coordinates)
                ),
                ffi.NULL,
                ffi.NULL,
                ffi.NULL,
            )
        self.last_tabulation_seconds = float(
            time.perf_counter() - tabulation_started
        )
        self.tabulation_count += 1
        orientation_started = time.perf_counter()
        _orient_cell_tensor(
            self.context.element,
            tensor,
            self.context.cell_info,
        )
        self.last_orientation_seconds = float(
            time.perf_counter() - orientation_started
        )
        self.orientation_count += 1

    def setup_cached_tensor(self) -> None:
        started = time.perf_counter()
        self._tabulate_and_orient()
        self.setup_tabulation_seconds = self.last_tabulation_seconds
        self.setup_orientation_seconds = self.last_orientation_seconds
        self.setup_seconds += float(time.perf_counter() - started)

    def apply(self, values: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
        if self.retabulate or self.gemv_count == 0 and self.tabulation_count == 0:
            self._tabulate_and_orient()
        else:
            self.last_tabulation_seconds = 0.0
            self.last_orientation_seconds = 0.0
        gemv_started = time.perf_counter()
        result = self.tensor @ values
        gemv_seconds = float(time.perf_counter() - gemv_started)
        self.gemv_count += 1
        return result, {
            "tabulation_seconds": float(self.last_tabulation_seconds),
            "orientation_seconds": float(self.last_orientation_seconds),
            "gemv_seconds": gemv_seconds,
        }


def _measure_path(
    path: _DenseCellPath,
    values: np.ndarray,
    authority: np.ndarray,
) -> dict[str, Any]:
    started = time.perf_counter()
    first, first_breakdown = path.apply(values)
    first_seconds = float(time.perf_counter() - started)
    repeated_seconds = []
    repeated_outputs = []
    repeated_breakdowns = []
    for _ in range(REPEATS):
        started = time.perf_counter()
        output, breakdown = path.apply(values)
        repeated_outputs.append(output)
        repeated_breakdowns.append(breakdown)
        repeated_seconds.append(float(time.perf_counter() - started))
    relative = float(
        np.linalg.norm(first - authority)
        / max(float(np.linalg.norm(authority)), 1.0e-30)
    )
    deterministic = all(np.array_equal(first, output) for output in repeated_outputs)
    vector_bytes = int(values.nbytes)
    tensor_bytes = int(path.tensor.nbytes)
    if path.retabulate:
        touched_bytes = 6 * tensor_bytes + 2 * vector_bytes
        touched_formula = (
            "6*tensor_bytes + 2*vector_bytes; deterministic per-apply "
            "lower-bound estimate"
        )
        inventory = {
            "retained_cell_dense_matrix_count": 0,
            "cell_tensor_scratch_count": 1,
            "cell_tensor_scratch_reused": True,
            "exact_class_cached_dense_tensor_count": 0,
        }
    else:
        touched_bytes = tensor_bytes + 2 * vector_bytes
        touched_formula = (
            "tensor_bytes + 2*vector_bytes; deterministic per-apply "
            "lower-bound estimate"
        )
        inventory = {
            "retained_cell_dense_matrix_count": 1,
            "cell_tensor_scratch_count": 0,
            "cell_tensor_scratch_reused": False,
            "exact_class_cached_dense_tensor_count": 1,
        }
    median_breakdown = {
        field: float(median(item[field] for item in repeated_breakdowns))
        for field in first_breakdown
    }
    return {
        "setup_seconds": float(path.setup_seconds),
        "setup_breakdown_seconds": {
            "tabulation_seconds": float(path.setup_tabulation_seconds),
            "orientation_seconds": float(path.setup_orientation_seconds),
        },
        "first_apply_seconds": first_seconds,
        "first_apply_breakdown_seconds": first_breakdown,
        "median_repeated_apply_seconds": float(median(repeated_seconds)),
        "median_repeated_breakdown_seconds": median_breakdown,
        "retained_bytes": tensor_bytes,
        "touched_bytes_estimated": int(touched_bytes),
        "touched_bytes_estimate_formula": touched_formula,
        "finite": bool(
            np.all(np.isfinite(first))
            and all(np.all(np.isfinite(output)) for output in repeated_outputs)
        ),
        "deterministic": bool(deterministic),
        "relative_error_vs_dense_authority": relative,
        "apply_count": int(1 + REPEATS),
        "tabulation_count": int(path.tabulation_count),
        "orientation_count": int(path.orientation_count),
        "gemv_count": int(path.gemv_count),
        "global_matrix_materialized": False,
        **inventory,
    }


def _measure_rank_one_direct_action(
    context: _CellContext,
    authority: np.ndarray,
) -> dict[str, Any]:
    from src.solvers.hcurl_rank_one_form_action import HcurlRankOneFormAction

    action = HcurlRankOneFormAction(context.form_ufl, context.function_space)
    try:

        def timed_apply() -> tuple[np.ndarray, float]:
            started = time.perf_counter()
            output = action.apply(context.local_input)
            elapsed = float(time.perf_counter() - started)
            return np.asarray(output).copy(), elapsed

        first, first_seconds = timed_apply()
        repeated_outputs = []
        repeated_seconds = []
        for _ in range(REPEATS):
            output, elapsed = timed_apply()
            repeated_outputs.append(output)
            repeated_seconds.append(elapsed)
        audit = dict(action.audit)
        components = dict(audit["retained_numeric_payload_components"])
        retained_bytes = int(audit["retained_numeric_payload_total_bytes"])
        packed_bytes = int(audit["last_packed_coefficient_bytes"])
        touched_bytes = int(
            components["coefficient_function_local_array_bytes"]
            + components["output_buffer_bytes"]
            + packed_bytes
        )
    finally:
        action.destroy()
    observed = first
    relative = float(
        np.linalg.norm(observed - authority)
        / max(float(np.linalg.norm(authority)), 1.0e-30)
    )
    return {
        "qualification_scope": "single_cell_H1R1_only",
        "eligible_for_H1R2": "not_evaluated_until_p6_gate",
        "backend_identity": audit["backend"],
        "form_rank": int(audit["form_rank"]),
        "coefficient_count": int(audit["coefficient_count"]),
        "kernel_output_local_rows": int(audit["kernel_output_local_rows"]),
        "kernel_output_local_rows_semantics": audit[
            "kernel_output_local_rows_semantics"
        ],
        "local_owned_rows": int(audit["local_owned_rows"]),
        "local_ghost_rows": int(audit["local_ghost_rows"]),
        "local_storage_entries": int(audit["local_storage_entries"]),
        "global_rows": int(audit["global_rows"]),
        "output_shape": list(audit["kernel_output_shape"]),
        "setup_seconds": float(audit["setup_seconds"]),
        "first_apply_seconds": float(first_seconds),
        "median_repeated_apply_seconds": float(median(repeated_seconds)),
        "retained_bytes": retained_bytes,
        "retained_payload_per_exact_class_bytes": retained_bytes,
        "retained_numeric_payload_components": components,
        "touched_bytes_estimated": touched_bytes,
        "touched_bytes_estimate_formula": (
            "coefficient_function_local_array_bytes + output_buffer_bytes + "
            "packed_coefficients_bytes; deterministic per-apply "
            "lower-bound estimate"
        ),
        "last_packed_coefficient_bytes": packed_bytes,
        "last_packed_coefficient_shapes": audit[
            "last_packed_coefficient_shapes"
        ],
        "last_packed_coefficient_entry_count": audit[
            "last_packed_coefficient_entry_count"
        ],
        "per_apply_packed_coefficient_temporary": audit[
            "per_apply_packed_coefficient_temporary"
        ],
        "per_apply_bounded_temporary_bytes": audit[
            "per_apply_bounded_temporary_bytes"
        ],
        "finite": bool(
            np.all(np.isfinite(observed))
            and all(np.all(np.isfinite(value)) for value in repeated_outputs)
        ),
        "deterministic": bool(
            all(np.array_equal(observed, value) for value in repeated_outputs)
        ),
        "relative_error_vs_dense_authority": relative,
        "apply_count": int(audit["apply_count"]),
        "global_matrix_materialized": audit["global_matrix_materialized"],
        "dense_cell_tensor_materialized_per_apply": audit[
            "dense_cell_tensor_materialized_per_apply"
        ],
        "retained_dense_cell_tensor_count": audit[
            "retained_dense_cell_tensor_count"
        ],
        "cell_tensor_scratch_count": audit["cell_tensor_scratch_count"],
        "ordinary_default_changed": audit["ordinary_default_changed"],
    }


def run_cell_action_microbenchmark(
    degree: int,
    *,
    include_rank_one_action: bool = False,
) -> dict[str, Any]:
    """Run one fixed single-cell diagnostic for ``degree``."""

    context = _build_single_cell(degree)
    try:
        cached = _DenseCellPath(context, retabulate=False)
        cached.setup_cached_tensor()
        authority = cached.tensor @ context.local_input
        cached_record = _measure_path(cached, context.local_input, authority)
        del cached

        current = _DenseCellPath(context, retabulate=True)
        current_record = _measure_path(current, context.local_input, authority)
        del current

        result = {
            "degree": int(degree),
            "nloc": int(context.element.space_dimension),
            "repeats": REPEATS,
            "material_tags": sorted(int(tag) for tag in MATERIAL_COEFFICIENTS),
            "active_cell_tag": context.cell_tag,
            "class_identity": context.class_identity,
            "dense_p6_class_bytes": int(P6_DENSE_CLASS_BYTES),
            "a_current_dense_reassembly": current_record,
            "b_cached_dense_diagnostic": {
                **cached_record,
                "diagnostic_only": True,
                "h_refinement_scalability": "not_claimed",
                "eligible_for_H2": False,
            },
            "a_b_relative_error": current_record[
                "relative_error_vs_dense_authority"
            ],
        }
        if include_rank_one_action:
            result["c_rank_one_direct_action"] = _measure_rank_one_direct_action(
                context,
                authority,
            )
        return result
    finally:
        del context


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def evaluate_h1r1_qualification(
    record_or_measurements: dict[str, Any] | list[dict[str, Any]],
) -> dict[str, Any]:
    """Recompute the fixed H1R.1 Gate from compact raw measurement fields."""

    if isinstance(record_or_measurements, dict):
        measurements = record_or_measurements.get("measurements", [])
        source_identity = record_or_measurements.get("source_identity", {})
    else:
        measurements = record_or_measurements
        source_identity = {}
    degrees = tuple(sorted(item.get("degree") for item in measurements))
    degrees_exact = degrees == H1R_DEGREES
    by_degree = {item.get("degree"): item for item in measurements}
    per_degree: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for degree in H1R_DEGREES:
        measurement = by_degree.get(degree, {})
        nloc = measurement.get("nloc")
        current = measurement.get("a_current_dense_reassembly", {})
        cached = measurement.get("b_cached_dense_diagnostic", {})
        direct = measurement.get("c_rank_one_direct_action", {})
        relative_error = direct.get("relative_error_vs_dense_authority")
        payload_bytes = direct.get("retained_payload_per_exact_class_bytes")
        packed_shapes = direct.get("last_packed_coefficient_shapes")
        packed_entries = direct.get("last_packed_coefficient_entry_count")
        packed_bytes = direct.get("last_packed_coefficient_bytes")
        temporary_bytes = direct.get("per_apply_bounded_temporary_bytes")
        packed_shape_gate = bool(
            isinstance(packed_shapes, list)
            and isinstance(nloc, int)
            and packed_shapes
            and all(
                isinstance(shape, list)
                and shape
                and all(
                    isinstance(dimension, int)
                    and not isinstance(dimension, bool)
                    and dimension > 0
                    for dimension in shape
                )
                and math.prod(shape) <= nloc
                for shape in packed_shapes
            )
        )
        packed_closure_gate = bool(
            isinstance(packed_entries, int)
            and 0 <= packed_entries <= nloc
            and isinstance(packed_bytes, int)
            and isinstance(temporary_bytes, int)
            and packed_entries * np.dtype(np.complex128).itemsize == packed_bytes
            and temporary_bytes == packed_bytes
        )
        c_checks = {
            "qualification_scope": direct.get("qualification_scope")
            == "single_cell_H1R1_only",
            "backend_identity": direct.get("backend_identity")
            == H1R_DIRECT_BACKEND_IDENTITY,
            "form_rank": direct.get("form_rank") == 1,
            "coefficient_count": direct.get("coefficient_count") == 1,
            "apply_count": direct.get("apply_count") == 1 + REPEATS,
            "relative_error": bool(
                _finite_number(relative_error)
                and 0.0 <= float(relative_error) <= 1.0e-11
            ),
            "finite": direct.get("finite") is True,
            "deterministic": direct.get("deterministic") is True,
            "dense_cell_tensor_materialized_per_apply": direct.get(
                "dense_cell_tensor_materialized_per_apply"
            ) is False,
            "retained_dense_cell_tensor_count": direct.get(
                "retained_dense_cell_tensor_count"
            ) == 0,
            "cell_tensor_scratch_count": direct.get("cell_tensor_scratch_count")
            == 0,
            "global_matrix_materialized": direct.get("global_matrix_materialized")
            is False,
            "retained_payload_per_exact_class_bytes": bool(
                isinstance(payload_bytes, int)
                and payload_bytes > 0
                and payload_bytes <= H1R_PAYLOAD_LIMIT_BYTES
            ),
            "ordinary_default_changed": direct.get("ordinary_default_changed")
            is False,
            "per_apply_packed_coefficient_temporary": direct.get(
                "per_apply_packed_coefficient_temporary"
            ) is True,
            "packed_shapes": packed_shape_gate,
            "packed_entry_bytes_closure": packed_closure_gate,
        }
        b_checks = {
            "diagnostic_only": cached.get("diagnostic_only") is True,
            "h_refinement_scalability": cached.get("h_refinement_scalability")
            == "not_claimed",
            "eligible_for_H2": cached.get("eligible_for_H2") is False,
        }
        a_seconds = current.get("median_repeated_apply_seconds")
        c_seconds = direct.get("median_repeated_apply_seconds")
        speedup = (
            float(a_seconds) / float(c_seconds)
            if _finite_number(a_seconds)
            and _finite_number(c_seconds)
            and float(a_seconds) > 0.0
            and float(c_seconds) > 0.0
            else None
        )
        p6_speedup_gate = bool(
            degree != 6
            or (
                _finite_number(a_seconds)
                and _finite_number(c_seconds)
                and float(a_seconds) > 0.0
                and float(c_seconds) > 0.0
                and float(c_seconds) < 0.25 * float(a_seconds)
            )
        )
        checks = {
            **{f"c_{name}": value for name, value in c_checks.items()},
            **{f"b_{name}": value for name, value in b_checks.items()},
            "p6_speedup": p6_speedup_gate,
        }
        per_degree[str(degree)] = {
            "checks": checks,
            "c_checks": c_checks,
            "b_checks": b_checks,
            "speedup_a_over_c": speedup,
            "p6_speedup_gate_pass": p6_speedup_gate,
            "c_median_repeated_apply_seconds": c_seconds,
            "a_median_repeated_apply_seconds": a_seconds,
            "pass": bool(all(checks.values())),
        }
        problems.extend(
            f"degree_{degree}:{name}"
            for name, passed in checks.items()
            if not passed
        )
    source_starts = source_identity.get("source_at_start", {})
    source_ends = source_identity.get("source_at_end", {})
    start_sha = source_starts.get("source_commit_full_sha")
    end_sha = source_ends.get("source_commit_full_sha")
    source_clean = bool(
        isinstance(start_sha, str)
        and len(start_sha) == 40
        and start_sha == start_sha.lower()
        and all(character in "0123456789abcdef" for character in start_sha)
        and end_sha == start_sha
        and source_starts.get("tracked_source_dirty") is False
        and source_starts.get("source_worktree_dirty") is False
        and source_ends.get("tracked_source_dirty") is False
        and source_ends.get("source_worktree_dirty") is False
        and source_starts.get("nonignored_untracked_paths") == []
        and source_starts.get("worktree_status_porcelain") == []
        and source_ends.get("nonignored_untracked_paths") == []
        and source_ends.get("worktree_status_porcelain") == []
        and source_starts.get("git_error") is None
        and source_ends.get("git_error") is None
    )
    if not degrees_exact:
        problems.append("degrees_exact")
    if not source_clean:
        problems.append("source_stable_clean")
    overall_pass = bool(
        degrees_exact
        and source_clean
        and all(item["pass"] for item in per_degree.values())
    )
    return {
        "schema": "task037_extra_h1r1.qualification.v1",
        "status": "pass" if overall_pass else "gate_failed",
        "pass": overall_pass,
        "problems": problems,
        "degrees_exact": degrees_exact,
        "source_stable_clean": source_clean,
        "per_degree_checks": per_degree,
        "p6_speedup": per_degree.get("6", {}).get("speedup_a_over_c"),
        "eligible_for_H1R2": overall_pass,
    }


def _h1r1_environment() -> dict[str, Any]:
    import basix
    import dolfinx
    from mpi4py import MPI
    from petsc4py import PETSc
    import ffcx
    import ufl

    thread_keys = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )
    return {
        "sys_executable": sys.executable,
        "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
        "petsc_int_type": np.dtype(PETSc.IntType).name,
        "versions": {
            "dolfinx": str(getattr(dolfinx, "__version__", "unknown")),
            "basix": str(getattr(basix, "__version__", "unknown")),
            "ffcx": str(getattr(ffcx, "__version__", "unknown")),
            "ufl": str(getattr(ufl, "__version__", "unknown")),
        },
        "mpi_size": int(MPI.COMM_SELF.size),
        "communicator": "MPI.COMM_SELF",
        "thread_environment": {
            key: os.environ.get(key) for key in thread_keys
        },
    }


def _source_is_clean(source: Any) -> bool:
    return bool(
        source.source_commit_full_sha
        and not source.tracked_source_dirty
        and not source.nonignored_untracked_paths
    )


def run_h1r1(output: Path) -> int:
    """Run the fixed p2/p3/p4/p6 diagnostic and write compact raw JSON."""

    source_at_start = _inspect_candidate_source()
    measurements = [
        run_cell_action_microbenchmark(
            degree,
            include_rank_one_action=True,
        )
        for degree in H1R_DEGREES
    ]
    environment = _h1r1_environment()
    source_at_end = _inspect_candidate_source()
    source_identity = {
        "source_at_start": source_at_start.as_jsonable(),
        "source_at_end": source_at_end.as_jsonable(),
        "start_clean": _source_is_clean(source_at_start),
        "end_clean": _source_is_clean(source_at_end),
        "stable_clean": bool(
            _source_is_clean(source_at_start)
            and _source_is_clean(source_at_end)
            and source_at_start.source_commit_full_sha
            == source_at_end.source_commit_full_sha
        ),
    }
    output = Path(output)
    record = {
        "schema": "task037_extra_h1r1.raw.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_identity": source_identity,
        "environment": environment,
        "exact_command": [
            sys.executable,
            "-m",
            "benchmarks.run_task037_extra_h1r",
            "run",
            "--output",
            str(output),
        ],
        "scope": {
            "degrees": list(H1R_DEGREES),
            "repeats": REPEATS,
            "mpi_size": 1,
            "communicator": "MPI.COMM_SELF",
        },
        "measurements": measurements,
        "H2_locked": True,
        "MPI1_memory_target_evaluated": False,
    }
    record["qualification"] = evaluate_h1r1_qualification(record)
    record = attach_evidence_sha256(record)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0 if record["qualification"]["pass"] else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return run_h1r1(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
