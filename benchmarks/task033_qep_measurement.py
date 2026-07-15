"""Pure-Python planning contracts for Task033 high-order QEP measurements.

The expensive DOLFINx/SLEPc execution lives in
``benchmarks.run_task033_qep_matrix``.  This module deliberately has no
DOLFINx import so the 180-entry p/h/MPI plan, its memory vetoes, and its
fail-closed runtime contract can be audited on the Windows host.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from benchmarks.task033_resource_gates import scaled_gate_limits


DEGREES = (1, 2, 3, 4)
MESH_LEVELS_NM = (5.0, 3.0, 2.5, 2.0, 1.5)
MPI_SIZES = (1, 2, 4)
MATERIAL_KINDS = ("air", "lossy_homogeneous", "stage4_xy")
DEFAULT_REQUESTED_MODES = 8
LEFT_CANDIDATE_POOL_POLICY = "max_requested_plus_4_or_1p5x"
COMPLEX128_BYTES = 16


@dataclass(frozen=True, order=True)
class QepCandidate:
    """One independently launchable QEP measurement shard."""

    material_kind: str
    degree: int
    h_nm: float
    mpi_size: int

    def __post_init__(self) -> None:
        if self.material_kind not in MATERIAL_KINDS:
            raise ValueError(f"Unsupported material_kind: {self.material_kind!r}")
        if self.degree not in DEGREES:
            raise ValueError(f"degree must be one of {DEGREES}.")
        if float(self.h_nm) not in MESH_LEVELS_NM:
            raise ValueError(f"h_nm must be one of {MESH_LEVELS_NM}.")
        if self.mpi_size not in MPI_SIZES:
            raise ValueError(f"mpi_size must be one of {MPI_SIZES}.")

    @property
    def matrix_key(self) -> str:
        mesh = f"{self.h_nm:g}".replace(".", "p")
        return f"{self.material_kind}_p{self.degree}_h{mesh}_mpi{self.mpi_size}"

    @property
    def has_analytic_beta(self) -> bool:
        return self.material_kind in {"air", "lossy_homogeneous"}


def qep_candidates() -> tuple[QepCandidate, ...]:
    """Return the deterministic 3 x 4 x 5 x 3 Task033 QEP matrix."""

    return tuple(
        QepCandidate(material, degree, h_nm, mpi_size)
        for material in MATERIAL_KINDS
        for degree in DEGREES
        for h_nm in MESH_LEVELS_NM
        for mpi_size in MPI_SIZES
    )


def mixed_quad_local_dimension(degree: int) -> int:
    """Return the local N1curl(p) x Q(p) dimension on one quadrilateral."""

    if degree not in DEGREES:
        raise ValueError(f"degree must be one of {DEGREES}.")
    # Basix first-kind quadrilateral H(curl): 2*p*(p+1), plus Qp H1:
    # (p+1)^2.  This is an element-local dimension, not a global DoF count.
    return (degree + 1) * (3 * degree + 1)


def task033_left_candidate_pool_size(requested_modes: int) -> int:
    """Return the audited adjoint pool for a retained right-mode basis.

    Independent right and adjoint PEP solves can cut a degenerate cluster at
    different members when both request exactly the retained basis size.
    Task033 keeps the public right basis unchanged and oversamples only the
    transient adjoint candidate pool before matching.
    """

    requested = int(requested_modes)
    if requested < 2:
        raise ValueError("requested_modes must be at least two.")
    return max(requested + 4, math.ceil(1.5 * requested))


def conservative_cross_section_cells(h_nm: float) -> dict[str, int]:
    """Bound the reviewed 50 x 25 nm Stage-4 matching cross-section grid.

    The x partition preserves the two material-interface coordinates around
    the 17 nm line, so ``ceil(50/h)`` alone would undercount several levels.
    The result remains a pre-run bound; the measured record replaces it with
    the resolved mesh inventory.
    """

    h_nm = float(h_nm)
    if h_nm not in MESH_LEVELS_NM:
        raise ValueError(f"h_nm must be one of {MESH_LEVELS_NM}.")
    x_segments_nm = (16.5, 17.0, 16.5)
    nx = sum(math.ceil(length / h_nm) for length in x_segments_nm)
    ny = math.ceil(25.0 / h_nm)
    return {"nx": nx, "ny": ny, "cells": nx * ny}


def qep_memory_prediction(
    candidate: QepCandidate,
    *,
    requested_modes: int = DEFAULT_REQUESTED_MODES,
    left_candidate_modes: int | None = None,
    container_limit_gib: float | None = None,
) -> dict[str, Any]:
    """Return two independent conservative QEP memory centers.

    This is a component-level QEP estimate, not the Case091 Hybrid factor
    estimate.  It uses a discontinuous global-DoF upper bound and element
    dense-coupling upper bound, then separately estimates (A) four retained
    sparse coefficients plus PEP vectors and (B) a direct-factor workspace.
    MPI replication/communication overhead is applied to the total memory
    authority, so increasing ranks never makes the prediction look cheaper.
    """

    if requested_modes < 2:
        raise ValueError("requested_modes must be at least two.")
    left_candidates = (
        task033_left_candidate_pool_size(requested_modes)
        if left_candidate_modes is None
        else int(left_candidate_modes)
    )
    required_left_candidates = task033_left_candidate_pool_size(requested_modes)
    if left_candidates < required_left_candidates:
        raise ValueError(
            "left_candidate_modes must satisfy the audited Task033 "
            f"oversampling policy (at least {required_left_candidates})."
        )
    cells = conservative_cross_section_cells(candidate.h_nm)
    local_dimension = mixed_quad_local_dimension(candidate.degree)
    full_dof_upper = cells["cells"] * local_dimension
    reduced_dof_upper = full_dof_upper
    nnz_upper_per_matrix = cells["cells"] * local_dimension**2
    four_matrix_nnz_upper = 4 * nnz_upper_per_matrix

    # Complex scalar + 64-bit column index + conservative allocator/row
    # overhead.  The estimate is intentionally larger than raw PETSc payload.
    sparse_bytes_per_nnz = 32
    four_matrix_payload_bytes = four_matrix_nnz_upper * sparse_bytes_per_nnz
    # During the adjoint solve the retained right basis remains live while the
    # larger transient left pool is formed. Count full+reduced vectors for
    # both pools and size PEP workspace from the larger solve.
    retained_vectors = 2 * (requested_modes + left_candidates)
    pep_work_vectors = max(16, 2 * max(requested_modes, left_candidates) + 8)
    vector_bytes = (
        (retained_vectors + pep_work_vectors)
        * full_dof_upper
        * COMPLEX128_BYTES
    )
    rank_overhead = 1.0 + 0.08 * (candidate.mpi_size - 1)

    coefficient_vector_center_gib = (
        (four_matrix_payload_bytes + vector_bytes) * rank_overhead / 1024**3
        + 0.20
    )
    # Independent center B treats the largest coefficient as the direct
    # factor input and applies an explicit sparse-factor/work amplification.
    direct_factor_bytes = nnz_upper_per_matrix * sparse_bytes_per_nnz * 24
    direct_factor_center_gib = (
        (four_matrix_payload_bytes + direct_factor_bytes + vector_bytes)
        * rank_overhead
        / 1024**3
        + 0.25
    )
    higher_center = max(coefficient_vector_center_gib, direct_factor_center_gib)
    conservative_upper_gib = higher_center * 1.5 + 0.25
    limits = scaled_gate_limits(container_limit_gib)
    centers_pass = all(
        center <= float(limits["two_center_limit_gib"])
        for center in (coefficient_vector_center_gib, direct_factor_center_gib)
    )
    upper_pass = conservative_upper_gib <= float(
        limits["conservative_upper_limit_gib"]
    )
    return {
        "data_identity": "predicted_not_measured",
        "scope": "cross_section_qep_component_only",
        "resolved_cell_upper_bound": cells,
        "mixed_local_dimension": local_dimension,
        "full_dof_upper_bound": full_dof_upper,
        "reduced_dof_upper_bound": reduced_dof_upper,
        "nnz_upper_bound_per_matrix": nnz_upper_per_matrix,
        "four_matrix_nnz_upper_bound": four_matrix_nnz_upper,
        "sparse_bytes_per_nnz_assumption": sparse_bytes_per_nnz,
        "requested_modes": requested_modes,
        "left_candidate_modes": left_candidates,
        "left_candidate_pool_policy": LEFT_CANDIDATE_POOL_POLICY,
        "mpi_total_overhead_factor": rank_overhead,
        "centers_gib": {
            "four_sparse_coefficients_and_pep_vectors": (
                coefficient_vector_center_gib
            ),
            "direct_factor_workspace": direct_factor_center_gib,
        },
        "conservative_upper_gib": conservative_upper_gib,
        "two_centers_pass": centers_pass,
        "conservative_upper_pass": upper_pass,
        "prediction_gate_pass": centers_pass and upper_pass,
        "gate_limits": limits,
        "limitations": [
            "Element-dense NNZ and discontinuous DoF are conservative pre-run bounds.",
            "The prediction is QEP-component-only and is not a Hybrid launch gate.",
            "A measured shard must still use the live cgroup/RSS memory authority.",
        ],
    }


def _valid_sha(value: str | None, length: int) -> bool:
    if value is None or len(value) != length:
        return False
    return all(character in "0123456789abcdef" for character in value.lower())


def qep_runtime_preflight(
    candidate: QepCandidate,
    *,
    prediction: dict[str, Any],
    source_clean_verified: bool | None = None,
    verified_clean_sha: str | None = None,
    swap_activity_detected: bool | None = None,
    watchdog_enabled: bool | None = None,
    one_large_case_at_a_time: bool | None = None,
    high_order_core_evidence_sha256: str | None = None,
) -> dict[str, Any]:
    """Evaluate the fail-closed runtime contract for one measurement shard."""

    failures: list[str] = []
    if not prediction.get("prediction_gate_pass", False):
        failures.append("qep_memory_prediction_gate_failed")

    if source_clean_verified is None:
        failures.append("tracked_source_clean_unknown")
    elif not source_clean_verified:
        failures.append("tracked_source_not_clean")
    if not _valid_sha(verified_clean_sha, 40):
        failures.append("full_verified_clean_sha_missing_or_invalid")

    if swap_activity_detected is None:
        failures.append("swap_activity_state_unknown")
    elif swap_activity_detected:
        failures.append("swap_activity_detected")

    if watchdog_enabled is None:
        failures.append("watchdog_state_unknown")
    elif not watchdog_enabled:
        failures.append("watchdog_not_enabled")

    if one_large_case_at_a_time is None:
        failures.append("one_large_case_contract_unknown")
    elif not one_large_case_at_a_time:
        failures.append("one_large_case_contract_not_met")

    if candidate.degree >= 3 and not _valid_sha(
        high_order_core_evidence_sha256, 64
    ):
        failures.append("case090_high_order_core_evidence_missing_or_invalid")

    return {
        "source_clean_verified": source_clean_verified,
        "verified_clean_sha": verified_clean_sha,
        "swap_activity_detected": swap_activity_detected,
        "watchdog_enabled": watchdog_enabled,
        "one_large_case_at_a_time": one_large_case_at_a_time,
        "high_order_core_evidence_sha256": high_order_core_evidence_sha256,
        "runtime_contract_verified": not failures,
        "launch_eligible": not failures,
        "failures": failures,
        "default_behavior": "unknown_fail_closed",
        "one_shard_per_process_contract": True,
    }


def not_run_measurement_record(
    candidate: QepCandidate,
    *,
    prediction: dict[str, Any],
    preflight: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Build a schema-ready shard record without manufacturing numerics."""

    status = (
        "not_run_by_memory_gate"
        if not prediction["prediction_gate_pass"]
        else "not_run_runtime_contract"
    )
    return {
        "schema_version": "task033.case091.qep-measurement.v1",
        "record_type": "task033_qep_measurement_shard",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": status,
        "identity": {
            "is_pde_run": False,
            "is_solver_pass": False,
            "is_memory_measurement": False,
            "result_identity": "not_run",
            "ordinary_default_changed": False,
            "proves_0p7nm_feasible": False,
        },
        "candidate": asdict(candidate),
        "memory_prediction": prediction,
        "runtime_preflight": preflight,
        "provenance": provenance,
        "numerical_results": None,
        "resource_measurements": None,
        "gates": {
            "all_required_numerical_gates_pass": False,
            "not_evaluated_reason": status,
        },
    }


def build_qep_plan(
    *,
    requested_modes: int = DEFAULT_REQUESTED_MODES,
    container_limit_gib: float | None = None,
) -> dict[str, Any]:
    """Build the deterministic fail-closed 180-shard execution plan."""

    entries: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for candidate in qep_candidates():
        prediction = qep_memory_prediction(
            candidate,
            requested_modes=requested_modes,
            container_limit_gib=container_limit_gib,
        )
        preflight = qep_runtime_preflight(candidate, prediction=prediction)
        status = (
            "not_run_by_memory_gate"
            if not prediction["prediction_gate_pass"]
            else "not_run_runtime_contract"
        )
        counts[status] = counts.get(status, 0) + 1
        entries.append(
            {
                "matrix_key": candidate.matrix_key,
                "candidate": asdict(candidate),
                "analytic_beta_available": candidate.has_analytic_beta,
                "memory_prediction": prediction,
                "runtime_preflight": preflight,
                "launch_eligible": False,
                "execution_status": status,
                "result_identity": "not_run",
                "is_pde_run": False,
                "is_solver_pass": False,
                "numerical_results": None,
            }
        )

    return {
        "schema_version": "task033.case091.qep-plan.v1",
        "record_type": "task033_qep_measurement_plan",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": "not_run",
        "identity": {
            "is_pde_run": False,
            "is_solver_pass": False,
            "is_memory_measurement": False,
            "ordinary_default_changed": False,
            "proves_0p7nm_feasible": False,
            "scope": "QEP component measurement planning only",
        },
        "axes": {
            "material_kinds": list(MATERIAL_KINDS),
            "degrees": list(DEGREES),
            "h_nm": list(MESH_LEVELS_NM),
            "mpi_sizes": list(MPI_SIZES),
            "entry_count": len(entries),
        },
        "requested_modes": requested_modes,
        "runtime_contract": {
            "source_clean": None,
            "swap_activity_detected": None,
            "watchdog_enabled": None,
            "one_large_case_at_a_time": None,
            "p3_p4_case090_core_evidence": None,
            "default_behavior": "unknown_fail_closed",
        },
        "summary": {
            "entries": len(entries),
            "execution_status_counts": counts,
            "measured_entries": 0,
            "solver_pass_entries": 0,
        },
        "artifact_provenance": {
            "generator_module": "benchmarks.task033_qep_measurement",
            "runner_module": "benchmarks.run_task033_qep_matrix",
            "data_identity": "deterministic_prediction_and_not_run_plan",
        },
        "entries": entries,
        "limitations": [
            "The checked-in plan executes no PDE and contains no measured QEP values.",
            "Each eligible shard must be launched independently under an external watchdog.",
            "MPI2/MPI4 SLEPc/MUMPS behavior is measured, not inferred from serial runs.",
            "Not-run entries are never counted as solver passes.",
        ],
    }
