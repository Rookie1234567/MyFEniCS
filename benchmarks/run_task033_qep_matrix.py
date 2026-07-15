"""Guarded Task033 QEP p/h measurement-plan and single-shard runner.

With no ``--execute`` flag this command performs no DOLFINx import and writes
only the deterministic fail-closed matrix plan.  Formal measurements execute
exactly one material/p/h shard at the MPI size selected by ``mpiexec``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any

from benchmarks.task033_qep_measurement import (
    DEFAULT_REQUESTED_MODES,
    DEGREES,
    LEFT_CANDIDATE_POOL_POLICY,
    MATERIAL_KINDS,
    MESH_LEVELS_NM,
    MPI_SIZES,
    QepCandidate,
    build_qep_plan,
    not_run_measurement_record,
    qep_memory_prediction,
    qep_runtime_preflight,
    task033_left_candidate_pool_size,
)
from benchmarks.task033_qep_qualification import (
    LEFT_RIGHT_BETA_PAIR_RELATIVE_ERROR_MAX,
    RAISED_QUADRATURE_MATRIX_DELTA_MAX,
    apply_formal_preflight_gates,
    resource_authority_gate,
    source_identity_gate,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN_OUTPUT = (
    ROOT
    / "benchmarks"
    / "cases"
    / "091_hybrid_hp_adaptivity_feasibility"
    / "records"
    / "qep_matrix_plan.json"
)
DEFAULT_SHARD_OUTPUT = (
    ROOT / "benchmarks" / "artifacts" / "cases" / "091" / "qep_shard.json"
)

# A fixed physical Fourier dictionary makes the per-shard tracking payload
# comparable across different h meshes without gathering a full eigenvector or
# pretending that coefficient vectors from different function spaces can be
# dotted directly.  The aggregate performs the actual cross-h assignment.
TRACKING_FOURIER_ORDERS = tuple(
    (order_m, order_n)
    for order_m in range(-2, 3)
    for order_n in range(-2, 3)
)
TRACKING_COMPONENTS = ("Et_x", "Et_y", "Ez")


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    output = path if path.is_absolute() else ROOT / path
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _complex_json(value: complex) -> list[float]:
    value = complex(value)
    return [float(value.real), float(value.imag)]


def _full_hex_sha(value: str | None, length: int) -> bool:
    if value is None or len(value) != length:
        return False
    return all(character in "0123456789abcdef" for character in value.lower())


def _read_number(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if text == "max":
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _vmstat_swap_pages() -> tuple[int | None, int | None]:
    try:
        fields = {
            key: int(value)
            for key, value in (
                line.split(maxsplit=1)
                for line in Path("/proc/vmstat").read_text(encoding="utf-8").splitlines()
            )
        }
    except (OSError, ValueError):
        return None, None
    return fields.get("pswpin"), fields.get("pswpout")


def _current_rss_bytes() -> int | None:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _cgroup_snapshot() -> dict[str, float | int | None]:
    root = Path("/sys/fs/cgroup")
    current = _read_number(root / "memory.current")
    limit = _read_number(root / "memory.max")
    swap_current = _read_number(root / "memory.swap.current")
    return {
        "memory_current_bytes": current,
        "memory_current_gib": None if current is None else current / 1024**3,
        "memory_limit_bytes": limit,
        "memory_limit_gib": None if limit is None else limit / 1024**3,
        "swap_current_bytes": swap_current,
        "swap_current_gib": (
            None if swap_current is None else swap_current / 1024**3
        ),
    }


def _host_available_memory_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _resource_environment_snapshot() -> dict[str, Any]:
    cgroup = _cgroup_snapshot()
    host_available = _host_available_memory_bytes()
    pswpin, pswpout = _vmstat_swap_pages()
    return {
        **cgroup,
        "host_available_memory_bytes": host_available,
        "host_available_memory_gib": (
            None if host_available is None else host_available / 1024**3
        ),
        "pswpin_pages": pswpin,
        "pswpout_pages": pswpout,
    }


def _historical_peak_rss_mb() -> float:
    import resource

    # Linux ru_maxrss is KiB.  Formal records identify this unit explicitly.
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0


def _source_identity(comm, verified_clean_sha: str | None) -> dict[str, Any]:
    if comm.rank == 0:
        head = _git("rev-parse", "HEAD")
        branch = _git("branch", "--show-current")
        tracked_status = _git("status", "--short", "--untracked-files=no")
    else:
        head = None
        branch = None
        tracked_status = None
    head, branch, tracked_status = comm.bcast(
        (head, branch, tracked_status), root=0
    )
    verified = (
        _full_hex_sha(verified_clean_sha, 40)
        and head is not None
        and head.lower() == str(verified_clean_sha).lower()
        and tracked_status == ""
    )
    return {
        "commit_sha": head,
        "head_before_sha": head,
        "head_after_sha": None,
        "branch": branch,
        "verified_clean_sha": verified_clean_sha,
        "tracked_status_before": tracked_status,
        "tracked_status_after": None,
        "tracked_clean_before": tracked_status == "",
        "tracked_clean_after": None,
        "source_stable_during_run": False,
        "source_clean_verified": bool(verified),
        "verification": (
            "host_git_clean_full_sha_attestation"
            if verified
            else "not_verified_fail_closed"
        ),
    }


def _finalize_source_identity(comm, source: dict[str, Any]) -> dict[str, Any]:
    if comm.rank == 0:
        head_after = _git("rev-parse", "HEAD")
        status_after = _git("status", "--short", "--untracked-files=no")
    else:
        head_after = None
        status_after = None
    head_after, status_after = comm.bcast(
        (head_after, status_after), root=0
    )
    updated = {
        **source,
        "head_after_sha": head_after,
        "tracked_status_after": status_after,
        "tracked_clean_after": status_after == "",
    }
    updated["source_stable_during_run"] = bool(
        updated.get("head_before_sha") == head_after
        and updated.get("tracked_status_before") == ""
        and status_after == ""
    )
    updated["source_clean_verified"] = source_identity_gate(updated)["pass"]
    updated["verification"] = (
        "tracked_clean_full_sha_stable_before_and_after"
        if updated["source_clean_verified"]
        else "not_verified_fail_closed"
    )
    return updated


def _provenance(args: argparse.Namespace, source: dict[str, Any], mpi_size: int) -> dict[str, Any]:
    return {
        **source,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "command": "python -m benchmarks.run_task033_qep_matrix "
        + " ".join(shlex.quote(value) for value in sys.argv[1:]),
        "mpi_size": mpi_size,
        "container_image": args.container_image,
        "container_digest": args.container_digest,
        "host_environment_id": args.host_environment_id,
        "python_version": sys.version,
        "formal_record_requires_tracked_source_clean_commit": True,
    }


def _stage_memory(comm, stage: str) -> dict[str, Any]:
    rss_local = _current_rss_bytes()
    rss_values = comm.allgather(rss_local)
    rss_sum = (
        None
        if any(value is None for value in rss_values)
        else sum(int(value) for value in rss_values)
    )
    environments = comm.allgather(_resource_environment_snapshot())

    def all_values(name: str) -> list[int] | None:
        values = [environment.get(name) for environment in environments]
        if any(value is None for value in values):
            return None
        return [int(value) for value in values]

    cgroup_values = all_values("memory_current_bytes")
    limit_values = all_values("memory_limit_bytes")
    swap_values = all_values("swap_current_bytes")
    host_values = all_values("host_available_memory_bytes")
    cgroup_current = None if cgroup_values is None else max(cgroup_values)
    container_limit = None if limit_values is None else min(limit_values)
    swap_current = None if swap_values is None else max(swap_values)
    host_available = None if host_values is None else min(host_values)
    authority = (
        None
        if rss_sum is None or cgroup_current is None
        else max(rss_sum, cgroup_current)
    )
    return {
        "stage": stage,
        "simultaneous_live_worker_rss_sum_bytes": rss_sum,
        "simultaneous_live_worker_rss_sum_gib": (
            None if rss_sum is None else rss_sum / 1024**3
        ),
        "container_cgroup_current_bytes": cgroup_current,
        "container_cgroup_current_gib": (
            None if cgroup_current is None else cgroup_current / 1024**3
        ),
        "container_memory_limit_bytes": container_limit,
        "container_memory_limit_gib": (
            None if container_limit is None else container_limit / 1024**3
        ),
        "container_swap_current_bytes": swap_current,
        "container_swap_current_gib": (
            None if swap_current is None else swap_current / 1024**3
        ),
        "host_available_memory_bytes": host_available,
        "host_available_memory_gib": (
            None if host_available is None else host_available / 1024**3
        ),
        "memory_authority_bytes": authority,
        "memory_authority_gib": (
            None if authority is None else authority / 1024**3
        ),
        "memory_authority_semantics": (
            "max(simultaneous live MPI worker RSS sum, container cgroup current)"
        ),
    }


def _max_elapsed(comm, started: float) -> float:
    from mpi4py import MPI

    return float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))


def _matrix_info(matrix) -> dict[str, Any]:
    from petsc4py import PETSc

    try:
        info = matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
        info_scope = "PETSc_GLOBAL_SUM"
    except (AttributeError, TypeError):  # pragma: no cover - old petsc4py fallback
        info = matrix.getInfo()
        info_scope = "petsc4py_default"
    return {
        "shape": [int(value) for value in matrix.getSize()],
        "nnz_used": int(round(float(info["nz_used"]))),
        "matrix_memory_bytes": float(info["memory"]),
        "info_scope": info_scope,
    }


def _matrix_relative_difference(first, second) -> float:
    from petsc4py import PETSc

    difference = first.copy()
    try:
        difference.axpy(
            -1.0,
            second,
            structure=PETSc.Mat.Structure.DIFFERENT_NONZERO_PATTERN,
        )
        return float(
            difference.norm(PETSc.NormType.FROBENIUS)
            / max(first.norm(PETSc.NormType.FROBENIUS), 1.0e-30)
        )
    finally:
        difference.destroy()


def _stage_requires_termination(stage: dict[str, Any], limit_gib: float) -> bool:
    authority = stage.get("memory_authority_gib")
    return authority is None or float(authority) >= limit_gib


def _formal_resource_summary(
    stages: list[dict[str, Any]], swap_delta: dict[str, int | None]
) -> dict[str, Any]:
    def extrema(name: str, *, maximum: bool) -> int | None:
        values = [stage.get(name) for stage in stages]
        if not values or any(value is None for value in values):
            return None
        numbers = [int(value) for value in values]
        return max(numbers) if maximum else min(numbers)

    worker = extrema("simultaneous_live_worker_rss_sum_bytes", maximum=True)
    cgroup = extrema("container_cgroup_current_bytes", maximum=True)
    authority = (
        None if worker is None or cgroup is None else max(worker, cgroup)
    )
    return {
        "simultaneous_live_worker_rss_sum_bytes": worker,
        "container_cgroup_current_bytes": cgroup,
        "memory_authority_bytes": authority,
        "memory_authority_semantics": (
            "max(simultaneous live MPI worker RSS sum, container cgroup current)"
        ),
        "container_memory_limit_bytes": extrema(
            "container_memory_limit_bytes", maximum=False
        ),
        "host_available_memory_bytes": extrema(
            "host_available_memory_bytes", maximum=False
        ),
        "container_swap_current_bytes": extrema(
            "container_swap_current_bytes", maximum=True
        ),
        "pswpin_delta_pages": swap_delta.get("pswpin_delta_pages"),
        "pswpout_delta_pages": swap_delta.get("pswpout_delta_pages"),
    }


def _numerical_results(
    *,
    operators,
    modes,
    report,
    target: complex,
    analytic_beta: complex | None,
    assembly_seconds: float,
    solve_seconds: float,
    basis=None,
    classification_seconds: float | None = None,
) -> dict[str, Any]:
    if not modes:
        raise RuntimeError("SLEPc PEP converged no QEP modes.")
    selected = min(modes, key=lambda mode: abs(mode.beta - target))
    scalar_bytes = 16
    reduced_vector_bytes = sum(
        int(mode.right_reduced.getSize()) * scalar_bytes for mode in modes
    )
    full_vector_bytes = sum(
        int(mode.right_full.getSize()) * scalar_bytes for mode in modes
    )
    left_reduced_vector_bytes = (
        0
        if basis is None
        else sum(
            int(mode.left_reduced.getSize()) * scalar_bytes
            for mode in basis.modes
        )
    )
    left_full_vector_bytes = (
        0
        if basis is None
        else sum(
            int(mode.left_full.getSize()) * scalar_bytes
            for mode in basis.modes
        )
    )
    beta_error = (
        None
        if analytic_beta is None
        else float(abs(complex(selected.beta) - analytic_beta) / max(abs(analytic_beta), 1e-30))
    )
    four_matrices = {
        name: _matrix_info(matrix)
        for name, matrix in (
            ("K0", operators.K0),
            ("K1", operators.K1),
            ("K2", operators.K2),
            ("electric_mass", operators.electric_mass),
        )
    }

    return {
        "full_dof": int(operators.full_shape[0]),
        "reduced_dof": int(operators.reduced_shape[0]),
        "four_matrix_nnz": {
            name: info["nnz_used"] for name, info in four_matrices.items()
        },
        "four_matrix_nnz_total": sum(
            int(info["nnz_used"]) for info in four_matrices.values()
        ),
        "four_matrix_info": four_matrices,
        "selected_beta_per_nm": _complex_json(selected.beta),
        "analytic_beta_per_nm": (
            None if analytic_beta is None else _complex_json(analytic_beta)
        ),
        "analytic_beta_relative_error": beta_error,
        "polynomial_relative_residual": float(
            selected.polynomial_relative_residual
        ),
        "slepc_relative_error": float(selected.slepc_relative_error),
        "converged_eigenpairs": int(report.converged_modes),
        "requested_eigenpairs": int(report.requested_modes),
        "iteration_count": int(report.iteration_count),
        "convergence_reason": int(report.convergence_reason),
        "assembly_seconds_max_rank": assembly_seconds,
        "solve_seconds_max_rank": solve_seconds,
        "classification_seconds_max_rank": classification_seconds,
        "retained_eigenvector_bytes": {
            "right_reduced": reduced_vector_bytes,
            "right_full": full_vector_bytes,
            "left_reduced": left_reduced_vector_bytes,
            "left_full": left_full_vector_bytes,
            "total": (
                reduced_vector_bytes
                + full_vector_bytes
                + left_reduced_vector_bytes
                + left_full_vector_bytes
            ),
            "scalar_bytes": scalar_bytes,
            "full_vector_gathered_to_root": False,
        },
        "left_right_classification": (
            None
            if basis is None
            else {
                "right_polynomial_relative_residual_max": max(
                    float(mode.right.polynomial_relative_residual)
                    for mode in basis.modes
                ),
                "left_polynomial_relative_residual_max": max(
                    float(mode.left_polynomial_relative_residual)
                    for mode in basis.modes
                ),
                "biorthogonality_identity_error": float(
                    basis.max_identity_error
                ),
                "left_pair_relative_errors": [
                    float(value) for value in basis.left_pair_relative_errors
                ],
                "left_pair_relative_error_max": max(
                    float(value) for value in basis.left_pair_relative_errors
                ),
                "left_candidate_pool_policy": LEFT_CANDIDATE_POOL_POLICY,
                "right_requested_modes": int(report.requested_modes),
                "left_candidate_requested_modes": int(
                    basis.adjoint_solver_report.requested_modes
                ),
                "left_candidate_converged_modes": int(
                    basis.adjoint_solver_report.converged_modes
                ),
                "near_degenerate_groups": [
                    {
                        "indices": [int(index) for index in group.indices],
                        "beta_center_per_nm": _complex_json(group.beta_center),
                        "max_relative_beta_spread": float(
                            group.max_relative_beta_spread
                        ),
                        "overlap_condition": float(group.overlap_condition),
                        "normalization_method": group.normalization_method,
                        "post_normalization_identity_error": float(
                            group.post_normalization_identity_error
                        ),
                    }
                    for group in basis.groups
                ],
                "directions": [mode.direction for mode in basis.modes],
                "kinds": [mode.kind for mode in basis.modes],
                "passive_branch_valid": [
                    bool(mode.passive_branch_valid) for mode in basis.modes
                ],
                "full_vector_gathered": bool(basis.full_vector_gathered),
            }
        ),
        "quadrature": {
            "field_degree": int(operators.field_degree),
            "geometry_degree": int(operators.geometry_degree),
            "coefficient_degree": int(operators.coefficient_degree),
            "selected_degree": int(operators.quadrature_degree),
            "policy": str(operators.quadrature_policy),
        },
    }


def _normalized_complex_fingerprint(values) -> tuple[list[list[float]], float]:
    """Return JSON-safe normalized complex moments and their measured norm."""

    import numpy as np

    array = np.asarray(values, dtype=np.complex128)
    norm = float(np.linalg.norm(array))
    if not math.isfinite(norm) or norm <= 1.0e-14:
        raise RuntimeError(
            "Common Fourier mode fingerprint has zero or non-finite norm."
        )
    normalized = array / norm
    return ([_complex_json(value) for value in normalized], norm)


def _mode_tracking_compact_evidence(
    *,
    cfg,
    cross_section,
    spaces,
    basis,
    quadrature_degree: int,
) -> dict[str, Any]:
    """Measure common physical left/right moments for later cross-h tracking.

    Direct PETSc vector overlap is invalid across h because the distributed
    mixed spaces have different dimensions.  Every shard instead projects its
    actual right and left fields onto the same small physical Fourier
    dictionary.  Only scalar moments are reduced; full vectors stay
    distributed.  The aggregate, not this shard, assigns modes.
    """

    import numpy as np
    import ufl
    from dolfinx import fem
    from mpi4py import MPI
    from petsc4py import PETSc

    if basis is None or not basis.modes:
        raise RuntimeError("Patterned tracking requires a nonempty biorthogonal basis.")

    msh = cross_section.mesh
    comm = msh.comm
    field = fem.Function(spaces.mixed, name="task033_qep_tracking_probe")
    transverse, longitudinal = ufl.split(field)
    coordinate = ufl.SpatialCoordinate(msh)
    measure = ufl.Measure("dx", domain=msh)
    components = (transverse[0], transverse[1], longitudinal)
    forms = []
    for order_m, order_n in TRACKING_FOURIER_ORDERS:
        argument = (
            2.0 * np.pi * order_m * (coordinate[0] - float(cfg.x_min))
            / float(cfg.period_x)
            + 2.0 * np.pi * order_n * (coordinate[1] - float(cfg.y_min))
            / float(cfg.period_y)
        )
        probe = ufl.cos(argument) - PETSc.ScalarType(1j) * ufl.sin(argument)
        forms.extend(
            fem.form(
                component * probe * measure,
                form_compiler_options={
                    "quadrature_degree": int(quadrature_degree)
                },
            )
            for component in components
        )

    def fingerprint(vector) -> tuple[list[list[float]], float]:
        vector.copy(field.x.petsc_vec)
        field.x.scatter_forward()
        moments = [
            complex(comm.allreduce(fem.assemble_scalar(form), op=MPI.SUM))
            for form in forms
        ]
        return _normalized_complex_fingerprint(moments)

    mode_rows: list[dict[str, Any]] = []
    for index, mode in enumerate(basis.modes):
        right, right_norm = fingerprint(mode.right.right_full)
        left, left_norm = fingerprint(mode.left_full)
        mode_rows.append(
            {
                "mode_index": index,
                "beta_per_nm": _complex_json(mode.beta),
                "direction": str(mode.direction),
                "kind": str(mode.kind),
                "passive_branch_valid": bool(mode.passive_branch_valid),
                "right_fourier_fingerprint": right,
                "left_fourier_fingerprint": left,
                "right_moment_norm_before_normalization": right_norm,
                "left_moment_norm_before_normalization": left_norm,
                "qprime_left_right_overlap_after": _complex_json(
                    mode.qprime_overlap_after
                ),
            }
        )

    return {
        "schema_version": 1,
        "evidence_kind": "measured_common_fourier_left_right_mode_fingerprints",
        "status": "compact_input_ready_for_cross_h_aggregate",
        "assignment_performed_in_shard": False,
        "cross_h_vector_dot_performed": False,
        "cross_h_semantics": (
            "The aggregate recomputes assignment from beta and normalized "
            "common physical left/right Fourier moments; coefficient vectors "
            "from different h spaces are never dotted."
        ),
        "probe_orders": [list(value) for value in TRACKING_FOURIER_ORDERS],
        "components_per_order": list(TRACKING_COMPONENTS),
        "fingerprint_length": len(forms),
        "quadrature_degree": int(quadrature_degree),
        "mode_count": len(mode_rows),
        "modes": mode_rows,
        "full_eigenvector_gathered": False,
    }


def _destroy_modes(modes) -> None:
    for mode in modes:
        mode.destroy()


def _run_shard(
    args: argparse.Namespace,
    comm,
    candidate: QepCandidate,
    prediction: dict[str, Any],
    preflight: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    # Heavy imports are intentionally below the fail-closed preflight.
    import basix
    import dolfinx
    import mpi4py
    import numpy as np
    import petsc4py
    import slepc4py
    from mpi4py import MPI
    from petsc4py import PETSc
    from slepc4py import SLEPc

    from src.common.config_3d import target_stage4_config
    from src.modes.cross_section_spaces import (
        build_cross_section_spaces,
        build_matching_cross_section,
    )
    from src.modes.quadratic_beta_eigenproblem import (
        analytic_homogeneous_beta,
        assemble_quadratic_beta_operators,
        solve_quadratic_beta_modes,
    )
    from src.modes.mode_classification import (
        PoyntingFluxEvaluator,
        build_biorthogonal_mode_basis,
    )

    runtime_provenance = {
        **provenance,
        "runtime_versions": {
            "dolfinx": dolfinx.__version__,
            "basix": basix.__version__,
            "petsc4py": petsc4py.__version__,
            "slepc4py": slepc4py.__version__,
            "petsc": ".".join(str(value) for value in PETSc.Sys.getVersion()),
            "slepc": ".".join(str(value) for value in SLEPc.Sys.getVersion()),
            "mpi4py": mpi4py.__version__,
            "mpi_library": MPI.Get_library_version().strip(),
            "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
            "complex128_verified": np.dtype(PETSc.ScalarType)
            == np.dtype(np.complex128),
        },
    }

    memory_stages = [
        dict(args._preflight_stage),
        _stage_memory(comm, "pre_mesh"),
    ]
    termination = float(
        prediction["gate_limits"]["controlled_termination_gib"]
    )
    if _stage_requires_termination(memory_stages[-1], termination):
        return _terminated_record(
            candidate,
            prediction,
            preflight,
            runtime_provenance,
            memory_stages,
            "pre_mesh_memory_authority_at_or_above_termination",
        )

    cfg = target_stage4_config(degree=candidate.degree, h_nm=candidate.h_nm)
    started = time.perf_counter()
    cross_section = build_matching_cross_section(cfg, candidate.material_kind)
    spaces = build_cross_section_spaces(
        cross_section, transverse_degree=candidate.degree
    )
    mesh_seconds = _max_elapsed(comm, started)
    memory_stages.append(_stage_memory(comm, "post_mesh_spaces"))
    if _stage_requires_termination(memory_stages[-1], termination):
        return _terminated_record(
            candidate,
            prediction,
            preflight,
            runtime_provenance,
            memory_stages,
            "post_mesh_memory_authority_at_or_above_termination",
        )

    started = time.perf_counter()
    operators = assemble_quadratic_beta_operators(
        cfg,
        cross_section,
        spaces,
        quadrature_degree=None,
    )
    assembly_seconds = _max_elapsed(comm, started)
    memory_stages.append(_stage_memory(comm, "post_assembly"))
    if _stage_requires_termination(memory_stages[-1], termination):
        try:
            return _terminated_record(
                candidate,
                prediction,
                preflight,
                runtime_provenance,
                memory_stages,
                "post_assembly_memory_authority_at_or_above_termination",
            )
        finally:
            operators.destroy()

    if candidate.material_kind == "air":
        analytic_beta = analytic_homogeneous_beta(cfg, cfg.n_air)
        target = analytic_beta
    elif candidate.material_kind == "lossy_homogeneous":
        analytic_beta = analytic_homogeneous_beta(cfg, cfg.n_grating)
        target = analytic_beta
    else:
        analytic_beta = None
        target = analytic_homogeneous_beta(cfg, cfg.n_air)

    modes = []
    basis = None
    left_candidate_modes = int(args.left_candidate_modes)
    try:
        started = time.perf_counter()
        modes, report = solve_quadratic_beta_modes(
            operators,
            target=target,
            requested_modes=args.requested_modes,
        )
        solve_seconds = _max_elapsed(comm, started)
        started = time.perf_counter()
        basis = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            modes,
            adjoint_target=np.conj(target),
            requested_left_modes=left_candidate_modes,
            poynting_evaluator=PoyntingFluxEvaluator(
                cfg, cross_section, spaces
            ),
        )
        classification_seconds = _max_elapsed(comm, started)
        memory_stages.append(_stage_memory(comm, "post_solve"))
        numerics = _numerical_results(
            operators=operators,
            modes=modes,
            report=report,
            target=target,
            analytic_beta=analytic_beta,
            assembly_seconds=assembly_seconds,
            solve_seconds=solve_seconds,
            basis=basis,
            classification_seconds=classification_seconds,
        )
        if candidate.material_kind == "stage4_xy":
            try:
                compact_tracking = _mode_tracking_compact_evidence(
                    cfg=cfg,
                    cross_section=cross_section,
                    spaces=spaces,
                    basis=basis,
                    quadrature_degree=int(operators.quadrature_degree),
                )
                tracking_compact_ready = True
                tracking_failure = None
            except Exception as exc:
                compact_tracking = None
                tracking_compact_ready = False
                tracking_failure = f"{type(exc).__name__}: {exc}"
            numerics["cross_h_tracking"] = {
                "evidence_kind": "measured_per_shard_input_for_cross_h_tracking",
                "status": (
                    "compact_input_ready_for_aggregate"
                    if tracking_compact_ready
                    else "compact_input_unavailable_fail_closed"
                ),
                "aggregate_recomputation_required": True,
                "compact_evidence": compact_tracking,
                "failure": tracking_failure,
            }
            memory_stages.append(_stage_memory(comm, "post_tracking_compact"))
            if _stage_requires_termination(memory_stages[-1], termination):
                return _terminated_record(
                    candidate,
                    prediction,
                    preflight,
                    runtime_provenance,
                    memory_stages,
                    "tracking_compact_memory_authority_unreadable_or_at_termination",
                )
        else:
            tracking_compact_ready = True
            numerics["cross_h_tracking"] = {
                "evidence_kind": "not_applicable_analytic_material",
                "status": "not_applicable",
                "aggregate_recomputation_required": False,
                "compact_evidence": None,
                "failure": None,
            }
        raised_comparison: dict[str, Any]
        elevated = None
        try:
            raised_degree = int(operators.quadrature_degree) + 2
            raised_started = time.perf_counter()
            elevated = assemble_quadratic_beta_operators(
                cfg,
                cross_section,
                spaces,
                quadrature_degree=raised_degree,
            )
            raised_seconds = _max_elapsed(comm, raised_started)
            differences = {
                name: _matrix_relative_difference(first, second)
                for name, first, second in (
                    ("K0", operators.K0, elevated.K0),
                    ("K1", operators.K1, elevated.K1),
                    ("K2", operators.K2, elevated.K2),
                    (
                        "electric_mass",
                        operators.electric_mass,
                        elevated.electric_mass,
                    ),
                )
            }
            maximum_difference = max(differences.values())
            raised_comparison = {
                "required": True,
                "base_quadrature_degree": int(operators.quadrature_degree),
                "raised_quadrature_degree": raised_degree,
                "matrix_relative_differences": differences,
                "max_matrix_relative_difference": maximum_difference,
                "gate_max": RAISED_QUADRATURE_MATRIX_DELTA_MAX,
                "assembly_seconds_max_rank": raised_seconds,
                "pass": maximum_difference
                <= RAISED_QUADRATURE_MATRIX_DELTA_MAX,
                "failure": None,
            }
            memory_stages.append(_stage_memory(comm, "post_raised_quadrature"))
            if _stage_requires_termination(memory_stages[-1], termination):
                return _terminated_record(
                    candidate,
                    prediction,
                    preflight,
                    runtime_provenance,
                    memory_stages,
                    "raised_quadrature_memory_authority_unreadable_or_at_termination",
                )
        except Exception as exc:  # preserve a fail-closed shard record
            raised_comparison = {
                "required": True,
                "base_quadrature_degree": int(operators.quadrature_degree),
                "raised_quadrature_degree": int(operators.quadrature_degree) + 2,
                "matrix_relative_differences": None,
                "max_matrix_relative_difference": None,
                "gate_max": RAISED_QUADRATURE_MATRIX_DELTA_MAX,
                "assembly_seconds_max_rank": None,
                "pass": False,
                "failure": f"{type(exc).__name__}: {exc}",
            }
        finally:
            if elevated is not None:
                elevated.destroy()
        numerics["quadrature"]["raised_comparison"] = raised_comparison
        rss = comm.gather(
            {
                "rank": comm.rank,
                "historical_peak_rss_mb": _historical_peak_rss_mb(),
                "unit_source": "Linux_ru_maxrss_KiB_divided_by_1024",
            },
            root=0,
        )
        swap_end = _vmstat_swap_pages()
        swap_start = tuple(args._swap_start)
        swap_delta = {
            "pswpin_delta_pages": (
                None
                if swap_start[0] is None or swap_end[0] is None
                else swap_end[0] - swap_start[0]
            ),
            "pswpout_delta_pages": (
                None
                if swap_start[1] is None or swap_end[1] is None
                else swap_end[1] - swap_start[1]
            ),
        }
        no_swap = bool(
            all(value == 0 for value in swap_delta.values())
            and all(
                stage.get("container_swap_current_bytes") == 0
                for stage in memory_stages
            )
        )
        residual_pass = numerics["polynomial_relative_residual"] <= 1.0e-10
        classification = numerics["left_right_classification"]
        left_residual_pass = bool(
            classification is not None
            and classification["left_polynomial_relative_residual_max"]
            <= 1.0e-8
        )
        biorthogonality_pass = bool(
            classification is not None
            and classification["biorthogonality_identity_error"] <= 1.0e-6
        )
        left_right_beta_pair_pass = bool(
            classification is not None
            and classification["left_pair_relative_error_max"]
            <= LEFT_RIGHT_BETA_PAIR_RELATIVE_ERROR_MAX
        )
        analytic_error = numerics["analytic_beta_relative_error"]
        analytic_gate = (
            "not_applicable_patterned_cross_section"
            if analytic_error is None
            else bool(math.isfinite(analytic_error))
        )
        converged_pass = numerics["converged_eigenpairs"] > 0
        below_termination = all(
            item.get("memory_authority_gib") is not None
            and float(item["memory_authority_gib"]) < termination
            for item in memory_stages
        )
        formal_resource = _formal_resource_summary(memory_stages, swap_delta)
        formal_resource_pass = resource_authority_gate(formal_resource)["pass"]
        raised_quadrature_pass = raised_comparison["pass"] is True
        all_gates = (
            residual_pass
            and left_residual_pass
            and biorthogonality_pass
            and left_right_beta_pair_pass
            and converged_pass
            and no_swap
            and below_termination
            and formal_resource_pass
            and raised_quadrature_pass
            and tracking_compact_ready
            and (analytic_gate is True or isinstance(analytic_gate, str))
        )
        status = (
            "measured_shard_pass" if all_gates else "measured_shard_failed"
        )
        return {
            "schema_version": "task033.case091.qep-measurement.v2",
            "record_type": "task033_qep_measurement_shard",
            "case_id": "091_hybrid_hp_adaptivity_feasibility",
            "status": status,
            "identity": {
                "is_pde_run": True,
                "is_solver_pass": bool(all_gates),
                "is_memory_measurement": True,
                "result_identity": "measured_shard",
                "is_physical_qualification_record": False,
                "physical_qualified": False,
                "ordinary_default_changed": False,
                "proves_0p7nm_feasible": False,
            },
            "candidate": {
                "material_kind": candidate.material_kind,
                "degree": candidate.degree,
                "h_nm": candidate.h_nm,
                "mpi_size": candidate.mpi_size,
            },
            "memory_prediction": prediction,
            "runtime_preflight": preflight,
            "provenance": runtime_provenance,
            "numerical_results": {
                **numerics,
                "mesh_cells_xy": [int(value) for value in cross_section.mesh_cells],
                "mesh_space_seconds_max_rank": mesh_seconds,
            },
            "resource_measurements": {
                "stage_samples": memory_stages,
                "formal_resource_authority": formal_resource,
                "historical_peak_rss_by_rank": rss,
                "historical_rss_is_not_simultaneous_sum": True,
                "swap_page_deltas": swap_delta,
                "no_swap_during_shard": no_swap,
                "external_watchdog_required_during_blocking_pep": True,
                "memory_authority": (
                    "max(simultaneous live MPI worker RSS sum, container cgroup current)"
                ),
            },
            "gates": {
                "converged_eigenpair": converged_pass,
                "polynomial_relative_residual_le_1e-10": residual_pass,
                "left_polynomial_relative_residual_le_1e-8": (
                    left_residual_pass
                ),
                "biorthogonality_identity_error_le_1e-6": (
                    biorthogonality_pass
                ),
                "left_right_beta_pair_relative_error_le_1e-7": (
                    left_right_beta_pair_pass
                ),
                "analytic_beta_error_finite": analytic_gate,
                "no_swap": no_swap,
                "below_controlled_termination": below_termination,
                "formal_resource_authority_pass": formal_resource_pass,
                "raised_quadrature_pass": raised_quadrature_pass,
                "patterned_tracking_compact_ready": tracking_compact_ready,
                "single_shard_only_not_physical_qualification": True,
                "all_required_numerical_gates_pass": all_gates,
            },
        }
    finally:
        if basis is not None:
            basis.destroy()
        else:
            _destroy_modes(modes)
        operators.destroy()


def _terminated_record(
    candidate: QepCandidate,
    prediction: dict[str, Any],
    preflight: dict[str, Any],
    provenance: dict[str, Any],
    memory_stages: list[dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": "task033.case091.qep-measurement.v2",
        "record_type": "task033_qep_measurement_shard",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": "terminated_by_memory_gate",
        "identity": {
            "is_pde_run": True,
            "is_solver_pass": False,
            "is_memory_measurement": True,
            "result_identity": "terminated_not_pass",
            "is_physical_qualification_record": False,
            "physical_qualified": False,
            "ordinary_default_changed": False,
            "proves_0p7nm_feasible": False,
        },
        "candidate": {
            "material_kind": candidate.material_kind,
            "degree": candidate.degree,
            "h_nm": candidate.h_nm,
            "mpi_size": candidate.mpi_size,
        },
        "memory_prediction": prediction,
        "runtime_preflight": preflight,
        "provenance": provenance,
        "numerical_results": None,
        "resource_measurements": {
            "stage_samples": memory_stages,
            "termination_reason": reason,
            "external_watchdog_required_during_blocking_pep": True,
        },
        "gates": {
            "all_required_numerical_gates_pass": False,
            "not_evaluated_reason": reason,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan the Task033 QEP p/h/MPI matrix or execute exactly one "
            "fail-closed measurement shard."
        )
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--degree", type=int, choices=DEGREES)
    parser.add_argument("--h-nm", type=float, choices=MESH_LEVELS_NM)
    parser.add_argument("--material-kind", choices=MATERIAL_KINDS)
    parser.add_argument("--requested-modes", type=int, default=DEFAULT_REQUESTED_MODES)
    parser.add_argument(
        "--left-candidate-modes",
        type=int,
        help=(
            "Transient adjoint candidate pool. Execution requires at least "
            "the audited max(requested+4, ceil(1.5*requested)) policy."
        ),
    )
    parser.add_argument("--container-limit-gib", type=float)
    parser.add_argument("--verified-clean-sha")
    parser.add_argument("--no-swap-verified", action="store_true", default=None)
    parser.add_argument(
        "--watchdog-enabled-verified", action="store_true", default=None
    )
    parser.add_argument(
        "--one-large-case-verified", action="store_true", default=None
    )
    parser.add_argument("--high-order-core-evidence-sha256")
    parser.add_argument("--container-image", default="myfenics-stage4:task28")
    parser.add_argument(
        "--container-digest",
        default="sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d",
    )
    parser.add_argument(
        "--host-environment-id",
        default=os.environ.get("TASK033_HOST_ENVIRONMENT_ID", "SK-20260601OSDE"),
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.requested_modes < 2:
        raise SystemExit("--requested-modes must be at least two.")
    required_left_candidates = task033_left_candidate_pool_size(
        args.requested_modes
    )
    if args.left_candidate_modes is None:
        args.left_candidate_modes = required_left_candidates
    if args.left_candidate_modes < required_left_candidates:
        raise SystemExit(
            "--left-candidate-modes must satisfy the audited Task033 policy: "
            f"at least {required_left_candidates} for "
            f"--requested-modes {args.requested_modes}."
        )

    if not args.execute:
        output = DEFAULT_PLAN_OUTPUT if args.output is None else args.output
        _write_json(
            output,
            build_qep_plan(
                requested_modes=args.requested_modes,
                container_limit_gib=args.container_limit_gib,
            ),
        )
        print(json.dumps({"status": "not_run", "output": str(output)}))
        return

    missing = [
        name
        for name, value in (
            ("--degree", args.degree),
            ("--h-nm", args.h_nm),
            ("--material-kind", args.material_kind),
        )
        if value is None
    ]
    if missing:
        raise SystemExit("--execute requires " + ", ".join(missing))

    # mpi4py is required only for a real shard, never for host-side planning.
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    if comm.size not in MPI_SIZES:
        raise SystemExit(f"Task033 QEP shards require MPI size in {MPI_SIZES}.")
    candidate = QepCandidate(
        material_kind=args.material_kind,
        degree=args.degree,
        h_nm=args.h_nm,
        mpi_size=comm.size,
    )
    source = _source_identity(comm, args.verified_clean_sha)
    provenance = _provenance(args, source, comm.size)
    prediction = qep_memory_prediction(
        candidate,
        requested_modes=args.requested_modes,
        left_candidate_modes=args.left_candidate_modes,
        container_limit_gib=args.container_limit_gib,
    )
    swap_start = _vmstat_swap_pages()
    preflight_stage = _stage_memory(comm, "formal_preflight")
    cgroup_swap = preflight_stage.get("container_swap_current_bytes")
    swap_detected = (
        None
        if args.no_swap_verified is None
        or cgroup_swap is None
        or any(value is None for value in swap_start)
        else bool(cgroup_swap is not None and cgroup_swap > 0)
    )
    preflight = qep_runtime_preflight(
        candidate,
        prediction=prediction,
        source_clean_verified=source["source_clean_verified"],
        verified_clean_sha=args.verified_clean_sha,
        swap_activity_detected=swap_detected,
        watchdog_enabled=args.watchdog_enabled_verified,
        one_large_case_at_a_time=args.one_large_case_verified,
        high_order_core_evidence_sha256=args.high_order_core_evidence_sha256,
    )
    preflight_resource = _formal_resource_summary(
        [preflight_stage],
        {
            "pswpin_delta_pages": 0 if swap_start[0] is not None else None,
            "pswpout_delta_pages": 0 if swap_start[1] is not None else None,
        },
    )
    resource_preflight_gate = resource_authority_gate(preflight_resource)
    if not resource_preflight_gate["pass"]:
        failures = list(preflight["failures"])
        failures.extend(
            f"resource:{failure}"
            for failure in resource_preflight_gate["failures"]
        )
        preflight = {
            **preflight,
            "resource_authority_gate": resource_preflight_gate,
            "runtime_contract_verified": False,
            "launch_eligible": False,
            "failures": list(dict.fromkeys(failures)),
        }
    else:
        preflight = {
            **preflight,
            "resource_authority_gate": resource_preflight_gate,
        }
    output = DEFAULT_SHARD_OUTPUT if args.output is None else args.output
    if not preflight["launch_eligible"]:
        record = not_run_measurement_record(
            candidate,
            prediction=prediction,
            preflight=preflight,
            provenance=provenance,
        )
    else:
        args._swap_start = swap_start
        args._preflight_stage = preflight_stage
        record = _run_shard(
            args,
            comm,
            candidate,
            prediction,
            preflight,
            provenance,
        )

    finalized_source = _finalize_source_identity(comm, source)
    if isinstance(record.get("provenance"), dict):
        record["provenance"].update(finalized_source)
    formal_resource = (
        (record.get("resource_measurements") or {}).get(
            "formal_resource_authority"
        )
        if isinstance(record.get("resource_measurements"), dict)
        else None
    )
    if record["identity"].get("is_pde_run"):
        finalized_preflight = apply_formal_preflight_gates(
            record["runtime_preflight"],
            source=record.get("provenance"),
            resource=formal_resource,
        )
        record["runtime_preflight"] = finalized_preflight
        source_pass = finalized_preflight["source_identity_gate"]["pass"]
        record["gates"]["source_identity_stable_clean_pass"] = source_pass
        if not finalized_preflight["runtime_contract_verified"]:
            record["gates"]["all_required_numerical_gates_pass"] = False
            record["identity"]["is_solver_pass"] = False
            if record["status"] == "measured_shard_pass":
                record["status"] = "measured_shard_failed"

    if comm.rank == 0:
        _write_json(output, record)
        print(json.dumps({"status": record["status"], "output": str(output)}))
    if record["status"] in {"measured_shard_failed", "execution_failed"}:
        raise SystemExit(2)
    if record["status"] == "terminated_by_memory_gate":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
