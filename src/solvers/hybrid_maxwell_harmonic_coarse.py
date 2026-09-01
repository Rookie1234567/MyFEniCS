# Broad catches synchronize rank-local third-party failures before the next MPI collective.
# ruff: noqa: BLE001
"""Stage-B1 Maxwell-harmonic trace identity and symbolic memory audit."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import scipy.linalg as sla
from mpi4py import MPI
from petsc4py import PETSc

from .hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorFactory,
    AffineIsotropicMaxwellTensorSpec,
)
from .hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
    _orient_cell_tensor,
)
from .hybrid_adaptive_impedance_schwarz import (
    build_cell_active_trace_expansion,
)

STAGE_B1_RHO = 0.007865985598112241
STAGE_B1_RHO2 = 6.187372942970919e-05
K0 = 2.0 * np.pi / 5.0
HARD_MEMORY_BYTES = 45 * 2**30
METRIC_ACCURACY_GATE = 1.0e-10

__all__ = (
    "HARD_MEMORY_BYTES",
    "K0",
    "STAGE_B1_RHO",
    "STAGE_B1_RHO2",
    "build_stage_b1_harmonic_identity",
)


def _collective_error(
    comm: MPI.Intracomm,
    local_error: str | None,
    context: str,
) -> None:
    errors = comm.allgather(local_error)
    first = next((error for error in errors if error is not None), None)
    if first is not None:
        raise RuntimeError(f"{context}: {first}")


def _cell_tags(cell_tags: Any, owned_cells: int) -> dict[int, int]:
    if not hasattr(cell_tags, "indices") or not hasattr(cell_tags, "values"):
        values = np.asarray(cell_tags, dtype=np.int32)
        if values.shape != (owned_cells,):
            raise ValueError("B1 cell tags do not match owned cell count")
        return {cell: int(values[cell]) for cell in range(owned_cells)}
    indices = np.asarray(cell_tags.indices, dtype=np.int32)
    values = np.asarray(cell_tags.values, dtype=np.int32)
    if indices.shape != values.shape:
        raise ValueError("B1 cell-tag indices and values have different shapes")
    result: dict[int, int] = {}
    for cell, tag in zip(indices, values, strict=True):
        cell = int(cell)
        if 0 <= cell < owned_cells:
            if cell in result:
                raise ValueError(
                    f"B1 cell tag table repeats owned cell {cell}"
                )
            result[cell] = int(tag)
    if set(result) != set(range(owned_cells)):
        raise ValueError("B1 cell tags must cover every owned cell exactly once")
    return result


def _hermitian_metrics(matrix: np.ndarray) -> tuple[float, float, bool]:
    matrix = np.asarray(matrix, dtype=np.complex128)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("B1 metric must be square")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("B1 metric is non-finite")
    scale = max(float(np.linalg.norm(matrix)), 1.0e-300)
    defect = float(np.linalg.norm(matrix - matrix.conj().T) / scale)
    hermitian = (matrix + matrix.conj().T) * 0.5
    minimum = float(np.min(np.linalg.eigvalsh(hermitian)))
    positive_semidefinite = minimum >= -1.0e-10 * scale
    return defect, minimum, positive_semidefinite


def _rank_range(matrix: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    left, singular_values, _right = np.linalg.svd(matrix, full_matrices=False)
    if not singular_values.size or not np.isfinite(singular_values[0]):
        raise ValueError("B1 Gamma pairing has no finite singular maximum")
    singular_max = float(singular_values[0])
    if singular_max <= 0.0:
        raise ValueError("B1 Gamma pairing has zero singular maximum")
    tau = max(matrix.shape) * np.finfo(float).eps * singular_max
    rank = int(np.count_nonzero(singular_values > tau))
    if rank <= 0:
        raise ValueError("B1 Gamma pairing has no retained range")
    return left[:, :rank], {
        "rank": rank,
        "tau": float(tau),
        "singular_max": singular_max,
        "smallest_retained": float(singular_values[rank - 1]),
        "largest_discarded": (
            float(singular_values[rank]) if rank < len(singular_values) else None
        ),
        "gap": (
            float(singular_values[rank - 1] - singular_values[rank])
            if rank < len(singular_values)
            else None
        ),
    }


def _cell_metric_data(
    function_space: Any,
    condensed: Any,
    provider: Any,
    cell: int,
    patch: Mapping[str, Any],
    weights: np.ndarray,
    cell_tags: Mapping[int, int],
    excluded_facets: set[int],
    factory: AffineIsotropicMaxwellTensorFactory,
) -> dict[str, Any]:
    raw_rows, active_rows, expansion = build_cell_active_trace_expansion(
        condensed, cell
    )
    patch_rows = np.asarray(patch["rows"], dtype=PETSc.IntType)
    if not np.array_equal(active_rows, patch_rows):
        raise ValueError(
            f"B1 cell {cell} active rows differ from its patch rows"
        )
    mesh = function_space.mesh
    tdim = int(mesh.topology.dim)
    mesh.topology.create_connectivity(tdim, tdim - 1)
    connectivity = mesh.topology.connectivity(tdim, tdim - 1)
    expected_facets = tuple(int(value) for value in connectivity.links(cell))
    if len(expected_facets) != 6:
        raise ValueError(f"B1 cell {cell} does not have six mesh facets")
    _coordinates, widths = _canonical_axis_aligned_coordinates(
        mesh, cell, tolerance=1.0e-11
    )
    tensor = factory.tensor(tag=int(cell_tags[cell]), widths=tuple(widths))
    cell_info = np.asarray(
        mesh.topology.get_cell_permutation_info()[cell : cell + 1],
        dtype=np.uint32,
    )
    _orient_cell_tensor(function_space.element, tensor, cell_info)
    dimension = int(function_space.element.space_dimension)
    interior = np.asarray(
        function_space.element.basix_element.entity_dofs[tdim][0],
        dtype=np.int32,
    )
    trace_positions = np.setdiff1d(
        np.arange(dimension, dtype=np.int32), interior, assume_unique=True
    )
    if len(trace_positions) != len(raw_rows):
        raise ValueError("B1 element trace positions do not match recovery rows")
    recovery = condensed.interior_from_trace_by_class[
        condensed.cell_recovery_maps[cell].class_key
    ]
    if recovery.shape != (len(interior), len(raw_rows)):
        raise ValueError("B1 interior lifting has an unexpected shape")
    lifting = np.zeros((dimension, len(raw_rows)), dtype=np.complex128)
    lifting[trace_positions, :] = np.eye(len(raw_rows), dtype=np.complex128)
    lifting[interior, :] = recovery
    lifted = lifting @ expansion

    blocks = tuple(provider.stream_facet_trace_blocks(cell))
    if {int(item[0]) for item in blocks} != set(range(6)):
        raise ValueError("B1 provider did not return local facets 0 through 5")
    facet_by_local = {int(item[0]): item for item in blocks}
    if tuple(int(facet_by_local[index][1]) for index in range(6)) != expected_facets:
        raise ValueError("B1 provider facet entities differ from mesh connectivity")
    raw_mass = np.zeros((len(raw_rows), len(raw_rows)), dtype=np.complex128)
    gamma_raw = np.zeros_like(raw_mass)
    included = []
    for local_facet in range(6):
        _local, mesh_facet, block = facet_by_local[local_facet]
        block = np.asarray(block, dtype=np.complex128)
        if block.shape != raw_mass.shape or not np.all(np.isfinite(block)):
            raise ValueError("B1 oriented facet block has an invalid shape/value")
        raw_mass += block
        if int(mesh_facet) not in excluded_facets:
            gamma_raw += block
            included.append(int(mesh_facet))
    volume = lifted.conj().T @ tensor @ lifted
    mass_all = expansion.conj().T @ raw_mass @ expansion
    metric = volume + K0 * mass_all
    gamma = expansion.conj().T @ gamma_raw @ expansion
    return {
        "cell": int(cell),
        "weights": np.asarray(weights, dtype=np.float64).copy(),
        "metric": np.ascontiguousarray(metric),
        "gamma": np.ascontiguousarray(gamma),
        "included_mesh_facets": tuple(sorted(included)),
        "excluded_mesh_facets": tuple(
            sorted(set(expected_facets) - set(included))
        ),
        "facet_count": len(included),
    }


def _finish_patch(
    data: Mapping[str, Any],
    patch: Mapping[str, Any],
    solution: np.ndarray,
    solve_ratios: tuple[float, ...],
) -> dict[str, Any]:
    metric = np.asarray(data["metric"], dtype=np.complex128)
    weights = np.asarray(data["weights"], dtype=np.float64)
    if solution.shape[0] != metric.shape[0] or weights.shape != (metric.shape[0],):
        raise ValueError("B1 harmonic solution and PoU shapes do not match")
    if not np.all(np.isfinite(solution)) or not np.all(np.isfinite(weights)):
        raise ValueError("B1 harmonic lifting is non-finite")
    if np.any(weights <= 0.0):
        raise ValueError("B1 patch PoU contains a non-positive weight")
    range_audit = data.get("rank_audit")
    if not isinstance(range_audit, Mapping) or "rank" not in range_audit:
        raise ValueError("B1 patch is missing its single Gamma rank audit")
    rhs_count = int(range_audit["rank"])
    if solution.shape[1] != rhs_count or len(solve_ratios) != rhs_count:
        raise ValueError("B1 harmonic factor returned the wrong RHS count")
    B = solution.conj().T @ metric @ solution
    weighted = weights[:, None] * solution
    A = weighted.conj().T @ metric @ weighted
    g_defect, g_min, g_psd = _hermitian_metrics(metric)
    a_defect, a_min, a_psd = _hermitian_metrics(A)
    b_defect, b_min, b_psd = _hermitian_metrics(B)
    for name, defect in (
        ("G", g_defect),
        ("A", a_defect),
        ("B", b_defect),
    ):
        if not np.isfinite(defect) or defect > METRIC_ACCURACY_GATE:
            raise ValueError(
                f"B1 {name} Hermitian defect exceeds fixed gate: {defect:.3e}"
            )
    if not g_psd or not a_psd or not b_psd:
        raise ValueError("B1 G/A/B failed the positive-semidefinite audit")
    b_threshold = (
        max(B.shape) * np.finfo(float).eps * float(np.linalg.norm(B))
    )
    if not np.isfinite(b_min) or b_min <= b_threshold:
        raise ValueError("B1 B metric is not positive definite")
    eigenvalues, eigenvectors = sla.eigh(
        (A + A.conj().T) * 0.5,
        (B + B.conj().T) * 0.5,
        check_finite=True,
    )
    if not np.all(np.isfinite(eigenvalues)):
        raise ValueError("B1 generalized eigenvalues are non-finite")
    eigen_residual = 0.0
    a_norm = float(np.linalg.norm(A))
    b_norm = float(np.linalg.norm(B))
    for index in range(len(eigenvalues)):
        vector = eigenvectors[:, index]
        numerator = np.linalg.norm(A @ vector - eigenvalues[index] * B @ vector)
        denominator = (
            a_norm * np.linalg.norm(vector)
            + abs(eigenvalues[index]) * b_norm * np.linalg.norm(vector)
        )
        eigen_residual = max(
            eigen_residual, float(numerator / max(denominator, 1.0e-300))
        )
    b_orthogonality = float(
        np.linalg.norm(eigenvectors.conj().T @ B @ eigenvectors - np.eye(len(eigenvalues)))
    )
    solve_residual = float(max(solve_ratios))
    if not np.isfinite(solve_residual) or solve_residual > METRIC_ACCURACY_GATE:
        raise ValueError("B1 harmonic solve residual exceeds fixed accuracy gate")
    if not np.isfinite(eigen_residual) or eigen_residual > METRIC_ACCURACY_GATE:
        raise ValueError("B1 generalized eigen residual exceeds fixed accuracy gate")
    if not np.isfinite(b_orthogonality) or b_orthogonality > METRIC_ACCURACY_GATE:
        raise ValueError("B1 B-orthogonality exceeds fixed accuracy gate")
    b_condition = float(np.linalg.cond((B + B.conj().T) * 0.5))
    if not np.isfinite(b_condition):
        raise ValueError("B1 B metric condition is non-finite")
    selected = eigenvalues >= STAGE_B1_RHO2
    retained = eigenvalues[selected]
    discarded = eigenvalues[~selected]
    selection_gap = {
        "smallest_retained_minus_rho2": (
            float(np.min(retained) - STAGE_B1_RHO2) if retained.size else None
        ),
        "rho2_minus_largest_discarded": (
            float(STAGE_B1_RHO2 - np.max(discarded)) if discarded.size else None
        ),
    }
    return {
        "patch_id": tuple(int(value) for value in patch["patch_id"]),
        "cell": int(data["cell"]),
        "rows": int(metric.shape[0]),
        "gamma_facets": int(data["facet_count"]),
        "included_mesh_facets": list(data["included_mesh_facets"]),
        "excluded_mesh_facets": list(data["excluded_mesh_facets"]),
        "harmonic_solve_residual_max": solve_residual,
        "harmonic_solve_residual_count": len(solve_ratios),
        "accuracy_gate": METRIC_ACCURACY_GATE,
        "G_hermitian_defect": g_defect,
        "G_min_eigenvalue": g_min,
        "G_positive_semidefinite": g_psd,
        "A_hermitian_defect": a_defect,
        "A_min_eigenvalue": a_min,
        "A_positive_semidefinite": a_psd,
        "B_hermitian_defect": b_defect,
        "B_min_eigenvalue": b_min,
        "B_positive_threshold": b_threshold,
        "B_condition_estimate": b_condition,
        "B_positive_definite": True,
        "generalized_eigenvalue_count": len(eigenvalues),
        "eigen_residual": eigen_residual,
        "B_orthogonality_defect": b_orthogonality,
        "retained_rank": int(range_audit["rank"]),
        "rank_reveal": dict(range_audit),
        "selected_mode_count": int(np.count_nonzero(selected)),
        "smallest_retained_eigenvalue": (
            float(np.min(retained)) if retained.size else None
        ),
        "largest_discarded_eigenvalue": (
            float(np.max(discarded)) if discarded.size else None
        ),
        "selection_gap": selection_gap,
        "selected_column_definition": "D*T*q",
    }


def _petsc_local_memory(matrix: PETSc.Mat) -> int:
    info = matrix.getInfo(PETSc.Mat.InfoType.LOCAL)
    fallback = int(info.get("nz_used", 0)) * (
        np.dtype(PETSc.ScalarType).itemsize + 2 * np.dtype(PETSc.IntType).itemsize
    )
    return int(info.get("memory", fallback))


def _symbolic_memory_preflight(
    bare_f: PETSc.Mat,
    action: Any,
    patches: tuple[Mapping[str, Any], ...],
    audits: tuple[Mapping[str, Any], ...],
    comm: MPI.Intracomm,
    current_process_tree_baseline_bytes: int | None,
    current_process_tree_baseline_source: str,
    *,
    hard_memory_bytes: int | None = None,
    economical_failure_route: str | None = None,
    basis_in_live_baseline: bool = False,
    fine_live_vector_bytes: int | None = None,
    fine_live_vector_count: int | None = None,
    coarse_live_vector_bytes: int | None = None,
    coarse_live_vector_count: int | None = None,
) -> dict[str, Any]:
    effective_hard_memory_bytes = HARD_MEMORY_BYTES
    if hard_memory_bytes is not None:
        if (
            not isinstance(hard_memory_bytes, (int, np.integer))
            or isinstance(hard_memory_bytes, bool)
            or int(hard_memory_bytes) <= 0
        ):
            raise ValueError("hard_memory_bytes must be a positive integer")
        effective_hard_memory_bytes = int(hard_memory_bytes)

    support_by_id = {
        tuple(item["patch_id"]): tuple(int(row) for row in item["rows"])
        for item in patches
    }
    row_to_patches: dict[int, list[tuple[int, int]]] = {}
    for patch_id, rows in support_by_id.items():
        for row in rows:
            row_to_patches.setdefault(int(row), []).append(patch_id)
    local_pairs: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    local_error: str | None = None
    try:
        first, last = map(int, bare_f.getOwnershipRange())
        for row in range(first, last):
            columns, _values = bare_f.getRow(row)
            left = row_to_patches.get(row, ())
            for column in columns:
                right = row_to_patches.get(int(column), ())
                local_pairs.update((item, other) for item in left for other in right)
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    _collective_error(comm, local_error, "B1 bare-F structural graph")
    pair_packets = comm.allgather(tuple(sorted(local_pairs)))
    pairs = sorted({pair for packet in pair_packets for pair in packet})
    selected_counts = {
        tuple(item["patch_id"]): int(item["selected_mode_count"])
        for item in audits
    }
    ac_nnz_upper = int(
        sum(selected_counts[left] * selected_counts[right] for left, right in pairs)
    )
    complex_bytes = int(np.dtype(PETSc.ScalarType).itemsize)
    index_bytes = int(np.dtype(PETSc.IntType).itemsize)
    pointer_bytes = 8
    active_rows = int(bare_f.getSize()[0])
    selected_total = int(sum(selected_counts.values()))
    prolongation_nnz = int(
        sum(
            selected_counts[tuple(item["patch_id"])] * len(item["rows"])
            for item in patches
        )
    )
    fp_nnz_local = 0
    first, last = map(int, bare_f.getOwnershipRange())
    for row in range(first, last):
        columns, _values = bare_f.getRow(row)
        reachable = {
            patch_id
            for column in columns
            for patch_id in row_to_patches.get(int(column), ())
        }
        fp_nnz_local += sum(selected_counts[patch_id] for patch_id in reachable)
    fp_nnz_upper = int(comm.allreduce(fp_nnz_local, op=MPI.SUM))
    max_patch_workspace = 0
    for item in audits:
        rows = int(item["rows"])
        rank = int(item["retained_rank"])
        max_patch_workspace = max(
            max_patch_workspace,
            (4 * rows * rows + 2 * rows * rank + 4 * rank * rank)
            * complex_bytes
            + (rows + rank) * index_bytes,
        )
    p_values = prolongation_nnz * complex_bytes
    p_indices = prolongation_nnz * index_bytes
    ph_pointer = (selected_total + 1) * pointer_bytes
    fp_values = fp_nnz_upper * complex_bytes
    fp_indices = fp_nnz_upper * index_bytes
    fp_pointer = (active_rows + 1) * pointer_bytes
    ac_values = ac_nnz_upper * complex_bytes
    ac_indices = ac_nnz_upper * index_bytes
    ac_pointer = (selected_total + 1) * pointer_bytes
    p_pointer = (active_rows + 1) * pointer_bytes
    p_base = int(p_values + p_indices + p_pointer)
    ph_base = int(p_values + p_indices + ph_pointer)
    fp_base = int(fp_values + fp_indices + fp_pointer)
    ac_base = int(ac_values + ac_indices + ac_pointer)
    sparse_base_bytes = int(p_base + ph_base + fp_base + ac_base)
    extended_vector_budget = any(
        value is not None
        for value in (
            fine_live_vector_bytes,
            fine_live_vector_count,
            coarse_live_vector_bytes,
            coarse_live_vector_count,
        )
    )
    if extended_vector_budget and any(
        value is None
        for value in (
            fine_live_vector_bytes,
            fine_live_vector_count,
            coarse_live_vector_bytes,
            coarse_live_vector_count,
        )
    ):
        raise ValueError("all economical live-vector bytes/count values are required")
    if extended_vector_budget and any(
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        for value in (
            fine_live_vector_bytes,
            fine_live_vector_count,
            coarse_live_vector_bytes,
            coarse_live_vector_count,
        )
    ):
        raise ValueError("economical live-vector values must be non-negative integers")
    iterative_vectors = (
        int(fine_live_vector_bytes or 0) + int(coarse_live_vector_bytes or 0)
        if extended_vector_budget
        else selected_total * 5 * complex_bytes
    )
    action_diagnostics = action.diagnostics
    bare_f_memory_global = int(
        comm.allreduce(_petsc_local_memory(bare_f), op=MPI.SUM)
    )
    factor_bytes_global = int(action_diagnostics.get("factor_bytes_global", 0))
    petsc_baseline = bare_f_memory_global + factor_bytes_global
    baseline_known = (
        current_process_tree_baseline_bytes is not None
        and int(current_process_tree_baseline_bytes) >= 0
        and bool(str(current_process_tree_baseline_source))
    )
    declared_baseline = (
        int(current_process_tree_baseline_bytes)
        if baseline_known
        else 0
    )
    baseline_component = max(declared_baseline, petsc_baseline)
    components = {
        "regenerated_selected_basis_global": (
            0
            if basis_in_live_baseline
            else prolongation_nnz * complex_bytes
        ),
        "P": p_base,
        "P_H": ph_base,
        "F_times_P": fp_base,
        "P_H_times_F_times_P": ac_base,
        "PETSc_sparse_allocation_overhead": sparse_base_bytes,
        "iterative_vectors": int(iterative_vectors),
        "current_bare_F_and_class_factor_baseline": int(baseline_component),
        "one_patch_dense_workspace": int(max_patch_workspace),
        "MatProduct_transient": int(
            fp_values + fp_indices + fp_pointer + ac_values + ac_indices + ac_pointer
        ),
    }
    projected = int(sum(components.values())) if baseline_known else None
    known = bool(
        baseline_known
        and all(isinstance(value, int) and value >= 0 for value in components.values())
    )
    allowed = bool(
        known
        and selected_total > 0
        and projected is not None
        and projected < effective_hard_memory_bytes
    )
    decision = (
        known,
        allowed,
        projected,
        "none"
        if allowed
        else (
            economical_failure_route
            if economical_failure_route is not None
            else "paper_economical_variant_required"
        ),
        effective_hard_memory_bytes,
    )
    if any(item != decision for item in comm.allgather(decision)):
        raise RuntimeError("B1 memory allocation decision differs across ranks")
    result = {
        "allocation_allowed": allowed,
        "route": decision[3],
        "hard_memory_bytes": effective_hard_memory_bytes,
        "projected_peak_bytes_conservative": projected,
        "FP_nnz_upper": fp_nnz_upper,
        "Ac_nnz_upper": ac_nnz_upper,
        "allocation_decision_collective": True,
        "baseline_known": baseline_known,
        "current_process_tree_baseline_bytes": (
            int(current_process_tree_baseline_bytes)
            if baseline_known
            else None
        ),
        "current_process_tree_baseline_source": (
            str(current_process_tree_baseline_source) if baseline_known else "unavailable"
        ),
        "bare_F_memory_global": bare_f_memory_global,
        "factor_bytes_global": factor_bytes_global,
        "sparse_base_bytes": sparse_base_bytes,
        "components_bytes": components,
        "fixed_byte_model": {
            "complex_bytes": complex_bytes,
            "index_bytes": index_bytes,
            "pointer_bytes": pointer_bytes,
            "P_nnz_upper": prolongation_nnz,
            "P_row_pointer_entries_upper": active_rows + 1,
            "P_H_row_pointer_entries_upper": selected_total + 1,
            "FP_row_pointer_entries_upper": active_rows + 1,
            "Ac_row_pointer_entries_upper": selected_total + 1,
            "selected_mode_total": selected_total,
            "petsc_sparse_allocation_overhead_multiplier": 1.0,
            "Ac_formula": "sum(interacting ordered patch pairs) m_l*m_m",
            "FP_formula": "sum(local F row reachable patch modes), then MPI sum",
            "pointer_bounds_are_upper_bounds": True,
        },
        "structural_interaction_pair_count": len(pairs),
        "full_vector_numeric_allgather": False,
        "metadata_collective": "compact integer support/count/pair allgather",
        "distributed_prolongation_created": False,
        "coarse_matrix_created": False,
    }
    if extended_vector_budget or basis_in_live_baseline:
        result["fixed_live_vector_budget"] = {
            "basis_in_live_baseline": bool(basis_in_live_baseline),
            "fine_live_vector_bytes": int(fine_live_vector_bytes or 0),
            "fine_live_vector_count": int(fine_live_vector_count or 0),
            "coarse_live_vector_bytes": int(coarse_live_vector_bytes or 0),
            "coarse_live_vector_count": int(coarse_live_vector_count or 0),
            "vector_storage_model": (
                "2*global_length*sizeof(PETSc.ScalarType) per reserved vector"
            ),
        }
    return result


def build_stage_b1_harmonic_identity(
    function_space: Any,
    condensed: Any,
    bare_f: PETSc.Mat,
    action: Any,
    mass_provider: Any,
    cell_tags: Any,
    facet_tags: Any,
    external_facet_tag: int,
    *,
    current_process_tree_baseline_bytes: int | None = None,
    current_process_tree_baseline_source: str = "caller_declared",
) -> dict[str, Any]:
    if not isinstance(bare_f, PETSc.Mat):
        raise TypeError("B1 requires a PETSc bare-F matrix")
    if not hasattr(action, "patch_metadata") or not hasattr(
        action, "solve_patch_multi_rhs"
    ):
        raise TypeError("B1 action lacks the bounded multi-RHS API")
    if not hasattr(mass_provider, "stream_facet_trace_blocks") or not hasattr(
        mass_provider, "collective_audit"
    ):
        raise TypeError("B1 requires the exact streaming facet provider")
    comm = bare_f.getComm().tompi4py()
    mesh = function_space.mesh
    owned_cells = int(mesh.topology.index_map(mesh.topology.dim).size_local)
    tags = None
    excluded_facets: set[int] = set()
    local_error: str | None = None
    try:
        tags = _cell_tags(cell_tags, owned_cells)
        if not hasattr(facet_tags, "find"):
            raise TypeError("B1 requires actual mesh facet tags with find()")
        excluded_facets = {
            int(value) for value in facet_tags.find(int(external_facet_tag))
        }
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    _collective_error(comm, local_error, "B1 cell/facet metadata preflight")
    assert tags is not None
    local_error = None
    local_weights: dict[tuple[int, int], np.ndarray] = {}
    local_metadata: list[dict[str, Any]] = []
    try:
        for item in action.patch_metadata():
            patch_id = tuple(int(value) for value in item["patch_id"])
            rows = tuple(int(value) for value in item["rows"])
            weights = np.asarray(item["weights"], dtype=np.float64)
            if weights.shape != (len(rows),) or not np.all(np.isfinite(weights)):
                raise ValueError("B1 local patch PoU metadata is invalid")
            local_weights[patch_id] = weights.copy()
            local_metadata.append(
                {
                    "patch_id": patch_id,
                    "cell_index": int(item["cell_index"]),
                    "rows": rows,
                    "class_key": str(item["class_key"]),
                    "owner_rank": int(item["owner_rank"]),
                }
            )
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    _collective_error(comm, local_error, "B1 local patch metadata")
    packets = comm.allgather(local_metadata)
    patches = tuple(
        sorted(
            (dict(item) for packet in packets for item in packet),
            key=lambda item: tuple(item["patch_id"]),
        )
    )
    if len({tuple(item["patch_id"]) for item in patches}) != len(patches):
        raise RuntimeError("B1 patch metadata contains duplicate patch IDs")

    local_tags = sorted(set(tags.values()))
    factory: AffineIsotropicMaxwellTensorFactory | None = None
    local_error = None
    try:
        if local_tags:
            factory = AffineIsotropicMaxwellTensorFactory(
                function_space.element.basix_element,
                AffineIsotropicMaxwellTensorSpec(
                    curl_coefficient=1.0,
                    mass_coefficient_by_tag={tag: K0**2 for tag in local_tags},
                ),
            )
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    _collective_error(comm, local_error, "B1 positive tensor factory construction")
    local_audits: list[dict[str, Any]] = []
    for patch in patches:
        patch_id = tuple(int(value) for value in patch["patch_id"])
        origin = int(patch_id[0])
        data = None
        local_error: str | None = None
        if comm.rank == origin:
            try:
                cell = int(patch["cell_index"])
                if cell < 0 or cell >= owned_cells:
                    raise ValueError("B1 patch cell is not locally owned")
                weights = local_weights.get(patch_id)
                if weights is None:
                    raise ValueError("B1 patch origin has no local PoU weights")
                if factory is None:
                    raise ValueError("B1 patch origin has no local tensor factory")
                data = _cell_metric_data(
                    function_space,
                    condensed,
                    mass_provider,
                    cell,
                    patch,
                    weights,
                    tags,
                    excluded_facets,
                    factory,
                )
                rhs, rank_audit = _rank_range(data["gamma"])
                data["rhs"] = rhs
                data["rank_audit"] = rank_audit
            except Exception as exc:
                local_error = f"{type(exc).__name__}: {exc}"
        _collective_error(comm, local_error, "B1 patch metric construction")
        rhs_columns = None if comm.rank != origin else data["rhs"]
        solution, solve_ratios = action.solve_patch_multi_rhs(
            patch_id,
            str(patch["class_key"]),
            int(patch["owner_rank"]),
            rhs_columns,
        )
        local_error = None
        if comm.rank == origin:
            try:
                assert data is not None
                assert solution is not None and solve_ratios is not None
                local_audits.append(
                    _finish_patch(data, patch, solution, solve_ratios)
                )
            except Exception as exc:
                local_error = f"{type(exc).__name__}: {exc}"
        _collective_error(comm, local_error, "B1 harmonic metric/eigen audit")
        data = None
        solution = None
    provider_audit = None
    local_error = None
    try:
        provider_audit = mass_provider.collective_audit()
        if provider_audit["status"] != "verified_exact_provider":
            raise RuntimeError("B1 provider audit is not exact and complete")
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    _collective_error(comm, local_error, "B1 provider audit")
    assert provider_audit is not None
    audit_packets = comm.allgather(tuple(local_audits))
    audits = tuple(
        sorted(
            (dict(item) for packet in audit_packets for item in packet),
            key=lambda item: tuple(item["patch_id"]),
        )
    )
    if len(audits) != len(patches):
        raise RuntimeError("B1 did not produce one compact audit per patch")
    memory = _symbolic_memory_preflight(
        bare_f,
        action,
        patches,
        audits,
        comm,
        current_process_tree_baseline_bytes,
        current_process_tree_baseline_source,
    )
    selected_modes_per_patch_histogram: dict[str, int] = {}
    for item in audits:
        key = str(int(item["selected_mode_count"]))
        selected_modes_per_patch_histogram[key] = (
            selected_modes_per_patch_histogram.get(key, 0) + 1
        )
    return {
        "schema": "task040.v8.stage_b1.maxwell_harmonic_identity.v1",
        "status": (
            "stage_b1_exact_harmonic_identity_audited"
            if memory["allocation_allowed"]
            else "paper_economical_variant_required"
        ),
        "identity_pass": True,
        "rho": STAGE_B1_RHO,
        "rho2": STAGE_B1_RHO2,
        "k0": K0,
        "gamma_definition": "boundary(Omega_l) minus boundary(Omega)",
        "external_facet_exclusion": int(external_facet_tag),
        "local_impedance_operator": "existing_stage_a_patch_matrix_only",
        "energy_metric": "C^H L^H (Kcurl+k0^2*M+k0*Mt_all6) L C",
        "selected_column_definition": "D*T*q",
        "stage_b2_basis_lifecycle": (
            "regenerate_owner_local_selected_basis_after_preflight"
        ),
        "patch_count": len(patches),
        "selected_mode_count_total": int(
            sum(int(item["selected_mode_count"]) for item in audits)
        ),
        "selected_modes_per_patch_histogram": selected_modes_per_patch_histogram,
        "exact_provider_audit": provider_audit,
        "patch_audits": list(audits),
        "memory_preflight": memory,
        "full_vector_numeric_allgather": False,
        "patch_audit_collective": "compact scalar audits only; no FE/basis/weights",
        "distributed_prolongation_created": False,
        "coarse_matrix_created": False,
    }
