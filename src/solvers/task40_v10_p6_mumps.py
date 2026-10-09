"""All-q exact MUMPS factors for the Task40 V10 p6 periodic reference.

The four modal sparse matrices and their factors remain live together. MUMPS
setup uses the project's existing exact backend controls. Native factor
statistics and process-tree RSS remain separate evidence channels.
"""
from __future__ import annotations

from hashlib import sha256
import gc
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from scipy import sparse

from .augmented_reference_correction import (
    NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
    STRICT_ONLY,
    q_solve_limit,
)
from .task40_v10_p6_periodic_profile import (
    TASK40_V10_P6_PROFILE,
    Task40V10P6PeriodicProfile,
)


ALL_Q_RESIDENT = "ALL_Q_RESIDENT"
ONE_Q_REFACTOR_V19 = "ONE_Q_REFACTOR_V19"


def _sparse_content_sha256(matrix: sparse.spmatrix) -> str:
    """Hash the caller's sparse storage without canonicalizing or mutating it."""
    if not sparse.issparse(matrix):
        raise TypeError("all-q factor input must be a SciPy sparse matrix")
    h = sha256()
    h.update(str(getattr(matrix, "format", type(matrix).__name__)).encode("ascii"))
    h.update(np.asarray(matrix.shape, dtype=np.int64).tobytes())
    h.update(np.dtype(matrix.dtype).str.encode("ascii"))
    if all(hasattr(matrix, name) for name in ("data", "indices", "indptr")):
        arrays = (("indptr", matrix.indptr), ("indices", matrix.indices), ("data", matrix.data))
    elif all(hasattr(matrix, name) for name in ("row", "col", "data")):
        arrays = (("row", matrix.row), ("col", matrix.col), ("data", matrix.data))
    else:
        csr = matrix.tocsr(copy=True)
        arrays = (("indptr", csr.indptr), ("indices", csr.indices), ("data", csr.data))
    for name, values in arrays:
        contiguous = np.ascontiguousarray(values)
        h.update(name.encode("ascii"))
        h.update(contiguous.dtype.str.encode("ascii"))
        h.update(np.asarray(contiguous.shape, dtype=np.int64).tobytes())
        h.update(memoryview(contiguous).cast("B"))
    return h.hexdigest()


def _payload_bytes(csr: sparse.csr_matrix) -> int:
    return int(csr.data.nbytes + csr.indices.nbytes + csr.indptr.nbytes)


def _petsc_csr_int_preflight(
    shape: Sequence[int],
    nnz: int,
    indptr: np.ndarray,
    indices: np.ndarray,
    petsc_int_dtype: Any,
) -> dict[str, int | str]:
    """Check a SciPy CSR layout before narrowing its indices to PetscInt."""

    if len(shape) != 2:
        raise ValueError("PETSc CSR input must have a two-dimensional shape")
    rows, columns = (int(value) for value in shape)
    nonzeros = int(nnz)
    if rows < 0 or columns < 0 or nonzeros < 0:
        raise ValueError("PETSc CSR dimensions and NNZ cannot be negative")
    integer_dtype = np.dtype(petsc_int_dtype)
    if not np.issubdtype(integer_dtype, np.signedinteger):
        raise TypeError("PETSc.IntType must be a signed integer dtype")
    bounds = np.iinfo(integer_dtype)
    if rows > bounds.max or columns > bounds.max or nonzeros > bounds.max:
        raise OverflowError("PETSc CSR shape or NNZ exceeds PetscInt range")

    row_pointers = np.asarray(indptr)
    column_indices = np.asarray(indices)
    if (
        row_pointers.ndim != 1
        or column_indices.ndim != 1
        or not np.issubdtype(row_pointers.dtype, np.integer)
        or not np.issubdtype(column_indices.dtype, np.integer)
    ):
        raise TypeError("PETSc CSR indptr and indices must be one-dimensional integers")
    if row_pointers.size != rows + 1 or column_indices.size != nonzeros:
        raise ValueError("PETSc CSR indptr/indices lengths disagree with shape or NNZ")
    if row_pointers.size == 0 or int(row_pointers[0]) != 0:
        raise ValueError("PETSc CSR indptr must start at zero")
    if int(row_pointers[-1]) != nonzeros:
        raise ValueError("PETSc CSR indptr endpoint must equal NNZ")
    if np.any(row_pointers < 0) or np.any(row_pointers > bounds.max):
        raise OverflowError("PETSc CSR indptr entry exceeds PetscInt range")
    if np.any(row_pointers[1:] < row_pointers[:-1]):
        raise ValueError("PETSc CSR indptr must be monotone nondecreasing")
    if column_indices.size:
        min_column = int(np.min(column_indices))
        max_column = int(np.max(column_indices))
        if min_column < 0 or max_column >= columns:
            raise ValueError("PETSc CSR column index lies outside matrix dimensions")
        if min_column < bounds.min or max_column > bounds.max:
            raise OverflowError("PETSc CSR column index exceeds PetscInt range")
    return {
        "rows": rows,
        "columns": columns,
        "nnz": nonzeros,
        "petsc_int_dtype": integer_dtype.str,
        "petsc_int_max": int(bounds.max),
    }


def _factor_probe_residual_limit(strategy: str, actual_q_solve_limit: float) -> float:
    """Keep V15's factor-qualification probe strict while PC solves use 1e-8."""

    if strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15:
        return 1.0e-10
    return float(actual_q_solve_limit)


def full_p6_pre_release_output_inventory(full_storage_rows: int) -> dict[str, object]:
    """Bound known full-row recovery/residual arrays before factor release.

    ``evaluate_native_residual`` returns seven full-storage arrays. The fast and
    native result dictionaries coexist; a conservative eight-vector allowance
    covers the active paired residual calculation. The audit packet then holds
    six copied arrays, one PETSc full-solution vector, and one write staging
    vector. These are phase alternatives, so the larger peak is selected.
    """
    rows = int(full_storage_rows)
    if rows < 0:
        raise ValueError("full-storage row count cannot be negative")
    returned_arrays = (
        "storage_solution",
        "native_effective_rhs",
        "native_residual",
        "augmented_fe_residual",
        "schur_residual_injection",
        "derived_native_residual",
        "native_identity_difference",
    )
    result_count = len(returned_arrays)
    workspace_vectors = 8
    audit_copies = 6
    final_solution_vectors = 1
    packet_staging_vectors = 1
    evaluation_peak = 2 * result_count + workspace_vectors
    packet_peak = 2 * result_count + audit_copies + final_solution_vectors + packet_staging_vectors
    selected_peak = max(evaluation_peak, packet_peak)
    return {
        "full_storage_rows": rows,
        "complex128_itemsize": np.dtype(np.complex128).itemsize,
        "native_residual_result_full_rows_array_names": list(returned_arrays),
        "paired_action_workspace_full_rows_vector_equivalents": workspace_vectors,
        "pre_release_independent_audit_copy_count": audit_copies,
        "final_full_solution_petsc_vector_count": final_solution_vectors,
        "packet_write_staging_vector_count": packet_staging_vectors,
        "evaluation_peak_vector_equivalents": evaluation_peak,
        "packet_peak_vector_equivalents": packet_peak,
        "selected_peak_vector_equivalents": selected_peak,
        "pre_release_peak_bytes": int(rows * selected_peak * np.dtype(np.complex128).itemsize),
        "scope": "known full_rows recovery/residual/audit-save arrays; post-release and official-output phases have separate live gates",
    }


def _petsc_matrix_info(matrix) -> dict[str, int | float | None]:
    try:
        raw = matrix.getInfo()
    except Exception:
        return {"available": 0}
    result: dict[str, int | float | None] = {"available": 1}
    for key in ("nz_used", "nz_allocated", "nz_unneeded", "memory", "mallocs"):
        value = raw.get(key)
        if value is None or not np.isfinite(float(value)):
            result[key] = None
        elif key == "mallocs":
            result[key] = int(value)
        else:
            result[key] = float(value)
    return result


def _mumps_native_evidence(raw: Mapping[str, object], *, numeric_complete: bool) -> dict[str, object]:
    infog = raw.get("infog")
    infog = infog if isinstance(infog, Mapping) else {}
    raw_infog = {str(k): v for k, v in infog.items()}
    raw9 = raw_infog.get("9")
    corrected_entries = None
    if type(raw9) is int:
        from src.solvers.common_3d_solve import _corrected_mumps_factor_nnz
        corrected_entries = _corrected_mumps_factor_nnz("mumps", raw9)
    memory = None
    if numeric_complete and type(raw_infog.get("19")) is int and type(raw_infog.get("22")) is int:
        from src.runners.physical_p4_schur_v14 import _mumps_memory_observation
        try:
            memory = _mumps_memory_observation({"numeric_raw": {"infog": raw_infog}})
        except (RuntimeError, TypeError, ValueError):
            memory = None
    return {
        "raw_infog": raw_infog,
        "raw_rinfog": raw.get("rinfog"),
        "INFOG_9_corrected_entries_if_negative": corrected_entries,
        "INFOG_9_correction_source": (
            "mumps_infog_9_negative_millions" if corrected_entries is not None else None
        ),
        "INFOG_19_allocated_bytes_upper": (
            memory.get("infog19_allocated_bytes_upper") if memory else None
        ),
        "INFOG_22_used_bytes_upper": (
            memory.get("infog22_used_bytes_upper") if memory else None
        ),
        "memory_observation": memory,
        "process_tree_rss_bytes": None,
    }


class AllQExactMumps:
    factor_lifecycle_strategy = ALL_Q_RESIDENT

    def __init__(self, matrices: Mapping[int, sparse.spmatrix], *,
                 allocation_gate: Callable[[str, Mapping[str, object]], object | None],
                 event: Callable[[str, Mapping[str, object]], None] | None = None,
                 expected_shapes: Sequence[int] | None = None,
                 profile: Task40V10P6PeriodicProfile = TASK40_V10_P6_PROFILE,
                 reference_pc_strategy: str = STRICT_ONLY,
                 transform_bank=None,
                 inverse_borrowers: Mapping[str, object] | None = None,
                 full_storage_rows: int | None = None,
                 target_reference_rows_match: bool = False):
        from petsc4py import PETSc
        from src.runners.physical_p4_cell_condensed_v18 import _factor_factory_for_backend

        self.PETSc = PETSc
        if not isinstance(profile, Task40V10P6PeriodicProfile):
            raise TypeError("all-q factors require an explicit Task40 p6 periodic profile")
        self.profile = profile
        self.reference_pc_strategy = str(reference_pc_strategy)
        self.q_solve_limit = q_solve_limit(self.reference_pc_strategy)
        self.factor_probe_limit = _factor_probe_residual_limit(
            self.reference_pc_strategy, self.q_solve_limit
        )
        self.event = event or (lambda _name, _facts: None)
        self.transform_bank = transform_bank
        self.inverse_borrowers = dict(inverse_borrowers or {})
        self.full_storage_rows = None if full_storage_rows is None else int(full_storage_rows)
        self.target_reference_rows_match = bool(target_reference_rows_match)
        if self.full_storage_rows is not None and self.full_storage_rows < 0:
            raise ValueError("future full-storage row count cannot be negative")
        for label, borrower in self.inverse_borrowers.items():
            if not callable(getattr(borrower, "future_legacy_inverse_reserve", None)):
                raise TypeError(f"inverse borrower {label!r} has no legacy inverse inventory")
            if transform_bank is not None and getattr(borrower, "_transform_bank", None) is not transform_bank:
                raise ValueError(f"inverse borrower {label!r} does not share the supplied run-local bank")
        if not callable(allocation_gate):
            raise TypeError("an active process-tree allocation gate is required")
        self.gate = allocation_gate
        self.nq = profile.q_count
        self.row_counts = tuple(expected_shapes or profile.augmented_rows_per_q)
        if len(self.row_counts) != self.nq or set(matrices) != set(range(self.nq)):
            raise ValueError("every actual profile q matrix is required before factorization")
        self.matrices = {}
        self.factors = {}
        self.csr_matrices = {}
        self.source_matrices = {}
        self._input_bindings = {}
        self.calls = 0
        self.destroyed = False
        self._max_simultaneous_factors = 0
        self.audit = {
            "backend": "PETSc MUMPS exact",
            "profile": profile.name,
            "reference_pc_strategy": self.reference_pc_strategy,
            "q_true_residual_admission_limit": self.q_solve_limit,
            "factor_probe_true_residual_limit": self.factor_probe_limit,
            "q_true_residual_strict_limit": 1.0e-10,
            "all_q_required": list(range(self.nq)),
            "all_q_factors_retained_simultaneously": False,
            "all_q_factor_objects_live_simultaneously": False,
            "all_q_numeric_factors_true_residual_passed": False,
            "all_q_numeric_factors_strict_true_residual_passed": False,
            "factor_inputs": [],
            "factor_tests": [],
            "all_four_factors_retained_simultaneously": False,
            "all_four_factor_objects_live_simultaneously": False,
            "all_four_numeric_factors_true_residual_passed": False,
            "factors_live_count_current": 0,
            "max_simultaneous_factors": 0,
            "factor_fill_bytes": None,
            "process_tree_peak_rss_bytes": None,
            "native_memory_source": "MUMPS INFOG(19/22), raw and upper-bound decoded",
            "native_factor_entries_source": "MUMPS INFOG(9), negative million-entry encoding only",
            "factor_fill_prediction": None,
        }
        factory = _factor_factory_for_backend("exact")
        started = perf_counter()
        try:
            symbolic_states: dict[int, dict[str, object]] = {}
            symbolic_estimates: dict[int, int] = {}
            for q in range(self.nq):
                source = matrices[q]
                caller_hash = _sparse_content_sha256(source)
                if (sparse.isspmatrix_csr(source)
                        and source.has_canonical_format
                        and source.has_sorted_indices):
                    csr = source
                else:
                    csr = sparse.csr_matrix(source, copy=True)
                    csr.sum_duplicates()
                    csr.sort_indices()
                if not csr.has_canonical_format or not csr.has_sorted_indices:
                    raise ValueError(f"q={q} CSR must be canonical and sorted")
                n = self.row_counts[q]
                if csr.shape != (n, n):
                    raise ValueError(f"q={q} matrix shape {csr.shape} != {(n, n)}")
                if (csr.dtype != np.dtype(np.complex128)
                        or not np.isfinite(csr.data).all()
                        or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128)):
                    raise ValueError("exact p6 factors require finite complex128 matrices and PETSc")
                petsc_int_preflight = _petsc_csr_int_preflight(
                    csr.shape, csr.nnz, csr.indptr, csr.indices, PETSc.IntType
                )
                csr_hash = _sparse_content_sha256(csr)
                self.source_matrices[q] = source
                self.csr_matrices[q] = csr
                self._input_bindings[q] = {
                    "caller_input_sha256_before": caller_hash,
                    "factor_csr_sha256_before": csr_hash,
                }
                csr_payload = _payload_bytes(csr)
                resident = self._resident_factor_evidence()
                self.gate("before_mumps_factor", {
                    "q": q,
                    "retained_factor_count": len(self.factors),
                    "resident_numeric_mumps_facts": resident,
                    "matrix_shape": list(csr.shape),
                    "nnz": int(csr.nnz),
                    "petsc_int_preflight": petsc_int_preflight,
                    "matrix_payload_bytes": csr_payload,
                    "canonicalization_copy_bytes": (csr_payload if csr is not source else 0),
                    "caller_input_sha256": caller_hash,
                    "factor_csr_sha256": csr_hash,
                    "factor_fill_prediction": None,
                })
                # Explicit copies isolate PETSc conversion from caller-owned CSR storage.
                indptr = np.asarray(csr.indptr, dtype=PETSc.IntType).copy()
                indices = np.asarray(csr.indices, dtype=PETSc.IntType).copy()
                values = np.asarray(csr.data, dtype=PETSc.ScalarType).copy()
                conversion_peak_bytes = int(indptr.nbytes + indices.nbytes + values.nbytes)
                matrix = PETSc.Mat().createAIJ(
                    size=csr.shape, csr=(indptr, indices, values), comm=PETSc.COMM_SELF)
                # Register immediately so even assembly/factory failures clean up the matrix.
                self.matrices[q] = matrix
                matrix.assemble()
                del indptr, indices, values
                matrix_facts = _petsc_matrix_info(matrix)
                factor = factory(matrix)
                self.factors[q] = factor
                self._note_live_factor_count()
                symbolic_start = perf_counter()
                factor.symbolic(matrix)
                symbolic_seconds = perf_counter() - symbolic_start
                self._assert_input_identity(q, "after_symbolic")
                symbolic_info = factor.info(extra_indices=(16, 17, 22, 29), include_local=True)
                infog = symbolic_info.get("infog")
                if not isinstance(infog, Mapping):
                    raise RuntimeError(f"q={q} symbolic MUMPS INFOG is unavailable")
                info16, info17 = infog.get("16"), infog.get("17")
                if (
                    type(info16) is not int
                    or type(info17) is not int
                    or info16 < 0
                    or info17 < 0
                    or info16 != info17
                ):
                    raise RuntimeError(
                        f"q={q} symbolic INFOG(16/17) estimates are unsupported: "
                        f"{info16!r}, {info17!r}"
                    )
                estimate_bytes = int(1_000_000 * (1 + max(info16, info17)))
                symbolic_estimates[q] = estimate_bytes
                symbolic_native = _mumps_native_evidence(symbolic_info, numeric_complete=False)
                self.event("task40_v12_mumps_symbolic_q_complete", {
                    "q": q,
                    "matrix_shape": list(csr.shape),
                    "rows": int(csr.shape[0]),
                    "nnz": int(csr.nnz),
                    "caller_input_sha256": caller_hash,
                    "factor_csr_sha256": csr_hash,
                    "symbolic_elapsed_seconds": symbolic_seconds,
                    "raw_mumps_info": symbolic_info,
                    "raw_infog": symbolic_native["raw_infog"],
                    "decoded_infog16_mb": int(info16),
                    "decoded_infog17_mb": int(info17),
                    "symbolic_estimate_bytes_from_infog16_17": estimate_bytes,
                    "native_metrics": symbolic_native,
                    "petsc_matrix_info": matrix_facts,
                    "checkpoint_semantics": "per-q symbolic checkpoint before the next q begins",
                })
                symbolic_states[q] = {
                    "source": source,
                    "csr": csr,
                    "caller_hash": caller_hash,
                    "csr_hash": csr_hash,
                    "csr_payload": csr_payload,
                    "matrix": matrix,
                    "factor": factor,
                    "matrix_facts": matrix_facts,
                    "conversion_peak_bytes": conversion_peak_bytes,
                    "symbolic_info": symbolic_info,
                    "symbolic_seconds": symbolic_seconds,
                    "symbolic_estimate_bytes": estimate_bytes,
                }
                resident_after_symbolic = self._resident_factor_evidence(exclude_q=q)
                self.gate("after_mumps_symbolic_before_numeric", {
                    "q": q,
                    "retained_factor_count": len(self.factors),
                    "resident_numeric_mumps_facts": resident_after_symbolic,
                    "current_symbolic_mumps_info_raw": symbolic_info,
                    "current_symbolic_native_metrics": _mumps_native_evidence(
                        symbolic_info, numeric_complete=False),
                    "current_symbolic_estimate_bytes_from_INFOG16_17": estimate_bytes,
                    "symbolic_estimates_observed_so_far_by_q": {
                        str(key): value for key, value in symbolic_estimates.items()
                    },
                    "matrix_shape": list(csr.shape),
                    "matrix_nnz": int(csr.nnz),
                    "csr_payload_bytes": csr_payload,
                    "petsc_matrix_info": matrix_facts,
                    "csr_to_petsc_conversion_workspace_peak_bytes": conversion_peak_bytes,
                    "csr_to_petsc_conversion_workspace_bytes_current": 0,
                    "symbolic_factor_workspace_bytes": None,
                    "process_tree_rss_bytes": None,
                })
            # Numeric MUMPS allocations are forbidden until every q branch has
            # completed symbolic analysis and the measured per-q estimates are
            # admitted together with retained Krylov and recovery workspace.
            retained_rows = sum(self.row_counts)
            # Right FGMRES retains V_(m+1) and Z_m. Six additional reduced
            # vectors cover its residual/work/solution/checkpoint co-residents.
            krylov_basis_vector_count = 2 * (32 + 1)
            ksp_workspace_vector_count = 6
            vector_itemsize = np.dtype(np.complex128).itemsize
            future_krylov_basis_bytes = int(
                retained_rows * krylov_basis_vector_count * vector_itemsize
            )
            future_ksp_workspace_bytes = int(
                retained_rows * ksp_workspace_vector_count * vector_itemsize
            )
            future_krylov_bytes = future_krylov_basis_bytes + future_ksp_workspace_bytes
            bank_inverse_reserve = (
                self.transform_bank.future_inverse_reserve()
                if self.transform_bank is not None
                else {
                    "future_unique_inverse_payload_bytes": 0,
                    "future_single_inverse_workspace_bytes": 0,
                    "future_unique_inverse_template_count": 0,
                }
            )
            legacy_inverse_reserves = {
                str(label): borrower.future_legacy_inverse_reserve()
                for label, borrower in self.inverse_borrowers.items()
            }
            legacy_inverse_payload_bytes = sum(
                int(row["future_legacy_inverse_payload_bytes"])
                for row in legacy_inverse_reserves.values()
            )
            legacy_inverse_workspace_bytes = max(
                (int(row["future_legacy_single_inverse_workspace_bytes"])
                 for row in legacy_inverse_reserves.values()),
                default=0,
            )
            future_inverse_payload_bytes = (
                int(bank_inverse_reserve["future_unique_inverse_payload_bytes"])
                + legacy_inverse_payload_bytes
            )
            future_inverse_workspace_bytes = max(
                int(bank_inverse_reserve["future_single_inverse_workspace_bytes"]),
                legacy_inverse_workspace_bytes,
            )
            full_rows = int(self.full_storage_rows or 0)
            full_output_inventory = full_p6_pre_release_output_inventory(full_rows)
            future_full_p6_output_bytes = int(full_output_inventory["pre_release_peak_bytes"])
            ksp_plus_inverse_workspace = future_krylov_bytes + future_inverse_workspace_bytes
            full_output_plus_inverse_workspace = (
                future_full_p6_output_bytes + future_inverse_workspace_bytes
            )
            selected_nonfactor_phase_peak_bytes = max(
                ksp_plus_inverse_workspace,
                full_output_plus_inverse_workspace,
            )
            future_co_resident_peak_bytes = (
                future_inverse_payload_bytes + selected_nonfactor_phase_peak_bytes
            )
            self.gate("all_q_symbolic_before_any_numeric", {
                "q_symbolic_estimates_bytes": {
                    str(q): symbolic_estimates[q] for q in range(self.nq)
                },
                "all_q_symbolic_estimate_sum_bytes": int(sum(symbolic_estimates.values())),
                "all_q_symbolic_q_completed": set(symbolic_estimates) == set(range(self.nq)),
                "all_four_symbolic_q_completed": (
                    self.nq == 4 and set(symbolic_estimates) == set(range(self.nq))
                ),
                "future_retained_krylov_and_vector_bytes": future_krylov_bytes,
                "future_krylov_basis_bytes": future_krylov_basis_bytes,
                "future_ksp_workspace_vector_bytes": future_ksp_workspace_bytes,
                "future_full_p6_pre_release_recovery_output_bytes": future_full_p6_output_bytes,
                "full_storage_rows_for_future_recovery": full_rows,
                "pre_release_recovery_output_inventory": {
                    **full_output_inventory,
                    "actual_target_and_reference_full_rows_match_required": self.target_reference_rows_match,
                },
                "future_inverse_payload_bytes": future_inverse_payload_bytes,
                "future_inverse_single_operation_workspace_bytes": future_inverse_workspace_bytes,
                "future_inverse_workspace_concurrency": "one sequential entity inverse; bank/legacy workspaces do not overlap",
                "future_bank_inverse_reserve": bank_inverse_reserve,
                "future_legacy_inverse_reserves_by_collection": legacy_inverse_reserves,
                "future_ksp_plus_inverse_workspace_bytes": ksp_plus_inverse_workspace,
                "future_full_output_plus_inverse_workspace_bytes": full_output_plus_inverse_workspace,
                "selected_future_nonfactor_co_resident_phase": (
                    "KSP_with_inverse_workspace"
                    if ksp_plus_inverse_workspace >= full_output_plus_inverse_workspace
                    else "pre_release_full_p6_recovery_output_with_inverse_workspace"
                ),
                "selected_future_nonfactor_co_resident_peak_bytes": selected_nonfactor_phase_peak_bytes,
                "future_inverse_payload_plus_selected_phase_bytes": future_co_resident_peak_bytes,
                "retained_vector_count_upper_bound": krylov_basis_vector_count + ksp_workspace_vector_count,
                "krylov_basis_vector_count": krylov_basis_vector_count,
                "ksp_workspace_vector_count": ksp_workspace_vector_count,
                "retained_vector_inventory_rows": retained_rows,
                "FGMRES_restart": 32,
                "q_symbolic_mumps_info_raw_by_q": {
                    str(q): symbolic_states[q]["symbolic_info"] for q in range(self.nq)
                },
                "q_symbolic_native_metrics_by_q": {
                    str(q): _mumps_native_evidence(
                        symbolic_states[q]["symbolic_info"], numeric_complete=False
                    )
                    for q in range(self.nq)
                },
                "future_workspace_headroom_bytes": 128 << 20,
                "numeric_factors_to_be_retained_simultaneously": self.nq,
                "retained_q_matrix_rows": int(retained_rows),
                "admission_semantics": (
                    "sum(actual_per_q_INFOG16_17_estimates)+pending_inverse_payloads+"
                    "max(KSP_vectors_or_full_rows_recovery_output+one_sequential_inverse_workspace)+128MiB; "
                    "separate post-release and official-output gates avoid summing mutually exclusive stages"
                ),
            })

            for q in range(self.nq):
                state = symbolic_states[q]
                source = state["source"]
                csr = state["csr"]
                caller_hash = state["caller_hash"]
                csr_hash = state["csr_hash"]
                csr_payload = int(state["csr_payload"])
                matrix = state["matrix"]
                factor = state["factor"]
                matrix_facts = state["matrix_facts"]
                conversion_peak_bytes = int(state["conversion_peak_bytes"])
                symbolic_info = state["symbolic_info"]
                symbolic_seconds = float(state["symbolic_seconds"])
                n = self.row_counts[q]
                numeric_start = perf_counter()
                factor.numeric(matrix)
                numeric_seconds = perf_counter() - numeric_start
                self._assert_input_identity(q, "after_numeric")
                if factor.get_icntl(10) != 0 or factor.get_icntl(35) != 0:
                    raise ValueError("exact MUMPS refinement/storage controls changed")
                numeric_info = factor.info(extra_indices=(16, 17, 22, 29), include_local=True)
                native = _mumps_native_evidence(numeric_info, numeric_complete=True)
                self.event("task40_v12_mumps_numeric_q_complete", {
                    "q": q,
                    "matrix_shape": list(csr.shape),
                    "rows": int(csr.shape[0]),
                    "nnz": int(csr.nnz),
                    "caller_input_sha256": caller_hash,
                    "factor_csr_sha256": csr_hash,
                    "numeric_elapsed_seconds": numeric_seconds,
                    "raw_mumps_info": numeric_info,
                    "raw_infog": native["raw_infog"],
                    "infog19_allocated_bytes_upper": native["INFOG_19_allocated_bytes_upper"],
                    "infog22_used_bytes_upper": native["INFOG_22_used_bytes_upper"],
                    "infog9_factor_entries": native["INFOG_9_corrected_entries_if_negative"],
                    "infog9_raw": native["raw_infog"].get("9"),
                    "native_metrics": native,
                    "checkpoint_semantics": "per-q numeric INFOG checkpoint before the probe solve",
                })
                rhs = np.cos(.23*np.arange(n)) + 1j*np.sin(.37*np.arange(n))
                solution = self._solve_once(q, rhs)
                self._assert_input_identity(q, "after_probe_solve")
                residual = float(np.linalg.norm(csr @ solution-rhs)/np.linalg.norm(rhs))
                strict_passed = bool(np.isfinite(residual) and residual <= 1.0e-10)
                residual_passed = bool(
                    np.isfinite(residual) and residual <= self.factor_probe_limit
                )
                test = {
                    "q": q,
                    "rows": n,
                    "relative_true_residual": residual,
                    "strict_limit": 1.0e-10,
                    "strict_passed": strict_passed,
                    "limit": self.factor_probe_limit,
                    "probe_limit": self.factor_probe_limit,
                    "actual_q_solve_limit": self.q_solve_limit,
                    "admission_passed": residual_passed,
                    "bounded_inexact_only": bool(residual_passed and not strict_passed),
                    "reference_pc_strategy": self.reference_pc_strategy,
                    "symbolic_seconds": symbolic_seconds,
                    "numeric_seconds": numeric_seconds,
                    "ICNTL_10": factor.get_icntl(10),
                    "ICNTL_35": factor.get_icntl(35),
                    "process_tree_rss_bytes": None,
                }
                self.audit["factor_tests"].append(test)
                self.event("task40_v12_mumps_numeric_q_probe_complete", {
                    "q": q,
                    "matrix_shape": list(csr.shape),
                    "rows": n,
                    "nnz": int(csr.nnz),
                    "caller_input_sha256": caller_hash,
                    "factor_csr_sha256": csr_hash,
                    "numeric_elapsed_seconds": numeric_seconds,
                    "raw_mumps_info": numeric_info,
                    "raw_infog": native["raw_infog"],
                    "native_metrics": native,
                    "numeric_true_residual": residual,
                    "numeric_true_residual_limit": self.factor_probe_limit,
                    "numeric_true_residual_passed": residual_passed,
                    "factor_probe_limit": self.factor_probe_limit,
                    "actual_q_solve_limit": self.q_solve_limit,
                    "numeric_true_residual_strict_limit": 1.0e-10,
                    "numeric_true_residual_strict_passed": strict_passed,
                    "bounded_inexact_only": bool(residual_passed and not strict_passed),
                    "process_tree_rss_bytes": None,
                    "checkpoint_semantics": "probe residual checkpoint before resource-gate evaluation",
                })
                if not residual_passed:
                    raise ValueError(
                        f"q={q} exact MUMPS true residual failed under "
                        f"{self.reference_pc_strategy} factor probe: "
                        f"{residual} > {self.factor_probe_limit}"
                    )
                numeric_admission = self.gate("after_mumps_numeric_true_residual", {
                    "q": q,
                    "current_q_symbolic_estimate_bytes": int(
                        state["symbolic_estimate_bytes"]
                    ),
                    "current_q_symbolic_INFOG16_17": {
                        "16": int(symbolic_info["infog"]["16"]),
                        "17": int(symbolic_info["infog"]["17"]),
                    },
                    "current_q_native_allocated_bytes_upper": native[
                        "INFOG_19_allocated_bytes_upper"
                    ],
                    "current_q_native_used_bytes_upper": native[
                        "INFOG_22_used_bytes_upper"
                    ],
                    "current_q_native_memory_observation": native["memory_observation"],
                    "resident_numeric_mumps_facts": self._resident_factor_evidence(),
                    "numeric_true_residual": residual,
                    "numeric_true_residual_limit": self.factor_probe_limit,
                    "numeric_true_residual_passed": True,
                    "factor_probe_limit": self.factor_probe_limit,
                    "actual_q_solve_limit": self.q_solve_limit,
                    "numeric_true_residual_strict_limit": 1.0e-10,
                    "numeric_true_residual_strict_passed": strict_passed,
                    "bounded_inexact_only": bool(not strict_passed),
                })
                numeric_rss = (
                    int(numeric_admission["current_process_tree_rss_bytes"])
                    if isinstance(numeric_admission, Mapping)
                    and numeric_admission.get("current_process_tree_rss_bytes") is not None
                    else None
                )
                native["process_tree_rss_bytes"] = numeric_rss
                test["process_tree_rss_bytes"] = numeric_rss
                self.event("task40_v12_mumps_numeric_q_admitted", {
                    "q": q,
                    "numeric_true_residual": residual,
                    "numeric_true_residual_limit": self.factor_probe_limit,
                    "numeric_true_residual_passed": True,
                    "factor_probe_limit": self.factor_probe_limit,
                    "actual_q_solve_limit": self.q_solve_limit,
                    "numeric_true_residual_strict_limit": 1.0e-10,
                    "numeric_true_residual_strict_passed": strict_passed,
                    "bounded_inexact_only": bool(not strict_passed),
                    "process_tree_rss_bytes": numeric_rss,
                    "resource_admission": numeric_admission,
                    "native_metrics": native,
                    "resident_numeric_mumps_facts": self._resident_factor_evidence(),
                })
                binding = self._input_bindings[q]
                binding["caller_input_sha256_after"] = _sparse_content_sha256(source)
                binding["factor_csr_sha256_after"] = _sparse_content_sha256(csr)
                self.audit["factor_inputs"].append({
                    "q": q,
                    "shape": list(csr.shape),
                    "nnz": int(csr.nnz),
                    "csr_payload_bytes": csr_payload,
                    "caller_input_sha256_before": caller_hash,
                    "caller_input_sha256_after": binding["caller_input_sha256_after"],
                    "factor_csr_sha256_before": csr_hash,
                    "factor_csr_sha256_after": binding["factor_csr_sha256_after"],
                    "input_identity_unchanged": True,
                    "factor_fill_bytes": None,
                    "native_allocated_bytes_upper": native["INFOG_19_allocated_bytes_upper"],
                    "native_used_bytes_upper": native["INFOG_22_used_bytes_upper"],
                    "native_factor_entries": native["INFOG_9_corrected_entries_if_negative"],
                    "native_factor_entries_raw_infog_9": native["raw_infog"].get("9"),
                    "native_memory_observation": native["memory_observation"],
                    "mumps_info_raw": numeric_info,
                    "process_tree_rss_bytes": numeric_rss,
                    "symbolic_mumps_info_raw": symbolic_info,
                    "symbolic_INFOG_16_mb": int(symbolic_info["infog"]["16"]),
                    "symbolic_INFOG_17_mb": int(symbolic_info["infog"]["17"]),
                    "symbolic_estimate_bytes_from_INFOG16_17": int(
                        state["symbolic_estimate_bytes"]
                    ),
                    "symbolic_seconds": symbolic_seconds,
                    "numeric_seconds": numeric_seconds,
                    "backend": "MUMPS",
                    "input_matrix_retained": True,
                    "petsc_matrix_info": matrix_facts,
                    "csr_to_petsc_conversion_workspace_peak_bytes": conversion_peak_bytes,
                })
                self.event("p6_all_q_mumps_factor_ready", {
                    "q": q,
                    "retained_factor_count": len(self.factors),
                    "native_mumps": native,
                    **test,
                })
            self.audit.update(
                setup_seconds=perf_counter()-started,
                all_q_factors_retained_simultaneously=(
                    self._max_simultaneous_factors == self.nq
                    and len(self.factors) == self.nq
                    and {int(row["q"]) for row in self.audit["factor_tests"]}
                    == set(range(self.nq))
                    and all(
                        np.isfinite(float(row["relative_true_residual"]))
                        and float(row["relative_true_residual"]) <= float(row["limit"])
                        for row in self.audit["factor_tests"]
                    )
                ),
                all_q_numeric_factors_true_residual_passed=(
                    {int(row["q"]) for row in self.audit["factor_tests"]}
                    == set(range(self.nq))
                    and all(bool(row["admission_passed"]) for row in self.audit["factor_tests"])
                ),
                all_q_numeric_factors_strict_true_residual_passed=(
                    {int(row["q"]) for row in self.audit["factor_tests"]}
                    == set(range(self.nq))
                    and all(bool(row["strict_passed"]) for row in self.audit["factor_tests"])
                ),
                all_q_factor_objects_live_simultaneously=(
                    self._max_simultaneous_factors == self.nq
                ),
                factors_live_count_current=len(self.factors),
                max_simultaneous_factors=self._max_simultaneous_factors,
                factor_fill_bytes=None,
                process_tree_peak_rss_bytes=None,
                factor_factory="physical_p4_cell_condensed_v18._factor_factory_for_backend('exact')",
            )
            self.audit.update(
                all_four_factors_retained_simultaneously=(
                    self.nq == 4 and self.audit["all_q_factors_retained_simultaneously"]
                ),
                all_four_numeric_factors_true_residual_passed=(
                    self.nq == 4 and self.audit["all_q_numeric_factors_true_residual_passed"]
                ),
                all_four_numeric_factors_strict_true_residual_passed=(
                    self.nq == 4 and self.audit["all_q_numeric_factors_strict_true_residual_passed"]
                ),
                all_four_factor_objects_live_simultaneously=(
                    self.nq == 4 and self.audit["all_q_factor_objects_live_simultaneously"]
                ),
            )
        except BaseException:
            try:
                self.destroy()
            except BaseException:
                pass
            raise

    def _note_live_factor_count(self) -> None:
        count = len(self.factors)
        self._max_simultaneous_factors = max(self._max_simultaneous_factors, count)
        self.audit["factors_live_count_current"] = count
        self.audit["max_simultaneous_factors"] = self._max_simultaneous_factors
        if count == self.nq:
            self.audit["all_q_factor_objects_live_simultaneously"] = True
            self.audit["all_four_factor_objects_live_simultaneously"] = self.nq == 4

    def _resident_factor_evidence(self, *, exclude_q: int | None = None) -> dict[str, object]:
        result: dict[str, object] = {}
        for q, factor in sorted(self.factors.items()):
            if q == exclude_q or factor.numeric_calls != 1:
                continue
            raw = factor.info(extra_indices=(9, 19, 22, 29), include_local=True)
            result[str(q)] = _mumps_native_evidence(raw, numeric_complete=True)
        return result

    def _assert_input_identity(self, q: int, stage: str) -> None:
        binding = self._input_bindings[q]
        if _sparse_content_sha256(self.source_matrices[q]) != binding["caller_input_sha256_before"]:
            raise RuntimeError(f"q={q} caller sparse input changed during {stage}")
        if _sparse_content_sha256(self.csr_matrices[q]) != binding["factor_csr_sha256_before"]:
            raise RuntimeError(f"q={q} factor CSR changed during {stage}")

    def _solve_once(self, q: int, rhs: np.ndarray) -> np.ndarray:
        PETSc = self.PETSc
        b = PETSc.Vec().createSeq(len(rhs), comm=PETSc.COMM_SELF)
        x = b.duplicate()
        try:
            b.array[:] = rhs
            self.factors[q].solve(b, x)
            return x.array.copy()
        finally:
            x.destroy()
            b.destroy()

    def solve(self, q: int, rhs: np.ndarray) -> np.ndarray:
        if self.destroyed or set(self.factors) != set(range(self.nq)):
            raise RuntimeError("all live profile p6 q factors are required")
        if type(q) is not int or q not in range(self.nq):
            raise ValueError(f"actual q branch index 0..{self.nq - 1} is required")
        values = np.asarray(rhs, dtype=np.complex128)
        if values.shape != (self.row_counts[q],) or not np.isfinite(values).all():
            raise ValueError("complete finite q-branch RHS required")
        PETSc = self.PETSc
        b = PETSc.Vec().createSeq(len(values), comm=PETSc.COMM_SELF)
        x = b.duplicate()
        try:
            b.array[:] = values
            self.factors[q].solve_repeated(b, x)
            self.calls += 1
            solution = x.array.copy()
        finally:
            x.destroy()
            b.destroy()
        return solution

    def verify_all_input_identities(self, *, stage: str = "final") -> dict[int, bool]:
        """Hash retained caller and factor CSR inputs once at a run boundary."""
        if self.destroyed:
            raise RuntimeError("cannot verify q matrix identity after factor cleanup")
        verified = {}
        for q in sorted(self.factors):
            self._assert_input_identity(q, stage)
            verified[q] = True
        self.audit["final_input_identity_checks"] = {
            "stage": str(stage),
            "q": sorted(verified),
            "passed": len(verified) == self.nq,
        }
        return verified

    def destroy(self) -> None:
        if self.destroyed:
            return
        if (
            len(self.factors) == self.nq
            and len(self.matrices) == self.nq
            and self.audit.get("all_q_numeric_factors_true_residual_passed") is True
        ):
            tests_by_q = {
                int(row["q"]): row for row in self.audit.get("factor_tests", ())
            }
            inputs_by_q = {
                int(row["q"]): row for row in self.audit.get("factor_inputs", ())
            }
            self.audit["pre_destroy_live_inventory"] = {
                "factor_q_indices": sorted(map(int, self.factors)),
                "matrix_q_indices": sorted(map(int, self.matrices)),
                "factor_live_count": len(self.factors),
                "all_q_factors_live": set(self.factors) == set(range(self.nq)),
                "factor_inventory_by_q": [
                    {
                        "factor_input": inputs_by_q[q],
                        "numeric_probe": tests_by_q[q],
                    }
                    for q in sorted(set(inputs_by_q).intersection(tests_by_q))
                ],
                "factor_inventory_timing": (
                    "historical per-q input and residual-probe records captured as each q completed"
                ),
                "current_native_factor_inventory_by_q": self._resident_factor_evidence(),
                "current_native_factor_inventory_timing": (
                    "read from each still-live numeric factor immediately before the first destroy call"
                ),
                "destroy_not_yet_started": True,
            }
            try:
                self.event(
                    "task40_v12_mumps_all_q_live_before_destroy",
                    self.audit["pre_destroy_live_inventory"],
                )
            except BaseException as exc:
                self.audit["pre_destroy_snapshot_error"] = {
                    "type": type(exc).__name__, "message": str(exc)
                }
        errors = []
        for q in reversed(sorted(self.factors)):
            factor = self.factors.pop(q)
            try:
                destroy = getattr(factor, "destroy", None)
                if callable(destroy):
                    destroy()
            except BaseException as exc:
                errors.append(exc)
            finally:
                self._note_live_factor_count()
        for q in reversed(sorted(self.matrices)):
            matrix = self.matrices.pop(q)
            try:
                matrix.destroy()
            except BaseException as exc:
                errors.append(exc)
        self.destroyed = True
        self.source_matrices.clear()
        self.csr_matrices.clear()
        self.matrices.clear()
        self._input_bindings.clear()
        self.audit["factors_live_count_current"] = len(self.factors)
        self.audit["max_simultaneous_factors"] = self._max_simultaneous_factors
        self.audit["all_q_factor_objects_live_simultaneously"] = (
            self._max_simultaneous_factors == self.nq
        )
        # Keep object-liveness historical, but never call a symbolic-only
        # object set a qualified four-q numeric factor set.
        self.audit["all_four_factor_objects_live_simultaneously"] = (
            self.nq == 4 and self._max_simultaneous_factors == self.nq
        )
        if errors:
            raise RuntimeError(f"failed to destroy {len(errors)} PETSc/MUMPS objects") from errors[0]

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.destroy()


class OneQRefactorV19Mumps:
    """Exact q factors with one live PETSc input matrix/factor slot.

    All immutable q CSR inputs are retained and hashed.  Symbolic analysis is
    first covered one q at a time, with each temporary PETSc/MUMPS object
    destroyed before the next q.  A factor cache miss rebuilds the symbolic
    and numeric factor from that retained CSR; it never rebuilds FE or Schur
    data.  This is a research-only lifecycle selected explicitly by V19.
    """

    factor_lifecycle_strategy = ONE_Q_REFACTOR_V19
    _SYMBOLIC_GUARD_MULTIPLIER = 4
    _FIXED_HEADROOM_BYTES = 128 << 20

    def __init__(
        self,
        matrices: Mapping[int, sparse.spmatrix],
        *,
        allocation_gate: Callable[[str, Mapping[str, object]], object | None],
        event: Callable[[str, Mapping[str, object]], None] | None = None,
        expected_shapes: Sequence[int] | None = None,
        profile: Task40V10P6PeriodicProfile = TASK40_V10_P6_PROFILE,
        reference_pc_strategy: str = STRICT_ONLY,
        transform_bank=None,
        inverse_borrowers: Mapping[str, object] | None = None,
        full_storage_rows: int | None = None,
        target_reference_rows_match: bool = False,
    ) -> None:
        self._setup_started = perf_counter()
        from petsc4py import PETSc
        from src.runners.physical_p4_cell_condensed_v18 import _factor_factory_for_backend

        if not isinstance(profile, Task40V10P6PeriodicProfile):
            raise TypeError("one-q factors require an explicit Task40 p6 periodic profile")
        if not callable(allocation_gate):
            raise TypeError("one-q factors require an active process-tree allocation gate")
        self.PETSc = PETSc
        self.profile = profile
        self.reference_pc_strategy = str(reference_pc_strategy)
        self.q_solve_limit = q_solve_limit(self.reference_pc_strategy)
        # V19 probes every newly built factor against the strict original
        # operator, even when the later PC-RHS admission is bounded-inexact.
        self.factor_probe_limit = 1.0e-10
        self.event = event or (lambda _name, _facts: None)
        self.gate = allocation_gate
        self.transform_bank = transform_bank
        self.inverse_borrowers = dict(inverse_borrowers or {})
        self.full_storage_rows = None if full_storage_rows is None else int(full_storage_rows)
        self.target_reference_rows_match = bool(target_reference_rows_match)
        if self.full_storage_rows is not None and self.full_storage_rows < 0:
            raise ValueError("future full-storage row count cannot be negative")
        for label, borrower in self.inverse_borrowers.items():
            if not callable(getattr(borrower, "future_legacy_inverse_reserve", None)):
                raise TypeError(f"inverse borrower {label!r} has no legacy inverse inventory")
            if transform_bank is not None and getattr(borrower, "_transform_bank", None) is not transform_bank:
                raise ValueError(f"inverse borrower {label!r} does not share the supplied run-local bank")

        self.nq = int(profile.q_count)
        self.row_counts = tuple(map(int, expected_shapes or profile.augmented_rows_per_q))
        required_q = set(range(self.nq))
        if len(self.row_counts) != self.nq or set(matrices) != required_q:
            raise ValueError("every actual profile q CSR input is required before one-q factorization")
        self.source_matrices: dict[int, sparse.spmatrix] = {}
        self.csr_matrices: dict[int, sparse.csr_matrix] = {}
        self._input_bindings: dict[int, dict[str, str]] = {}
        self.matrices: dict[int, Any] = {}
        self.factors: dict[int, Any] = {}
        # Probe Vecs are short-lived, but a failed native destroy means their
        # ownership cannot be treated as released. Keep both the owner and the
        # original exception reachable and refuse another factor slot.
        self._probe_cleanup_owners: list[tuple[str, Any, BaseException]] = []
        self.calls = 0  # Actual PC/startup RHS solves; probes are a separate category.
        self.destroyed = False
        self._max_simultaneous_factors = 0
        self._max_simultaneous_matrices = 0
        self._symbolic_estimates: dict[int, int] = {}
        self._symbolic_reports: dict[int, dict[str, Any]] = {}
        self._passed_factor_qs: set[int] = set()
        self._solved_qs: set[int] = set()
        self._factor_factory = _factor_factory_for_backend("exact")
        self.audit: dict[str, Any] = {
            "schema": "task40extra.review_v19_one_q_factor_lifecycle.v1",
            "factor_lifecycle_strategy": ONE_Q_REFACTOR_V19,
            "reference_pc_strategy": self.reference_pc_strategy,
            "profile": profile.name,
            "backend": "PETSc MUMPS exact",
            "q_true_residual_admission_limit": self.q_solve_limit,
            "factor_probe_true_residual_limit": self.factor_probe_limit,
            "all_q_required": list(range(self.nq)),
            "input_q_coverage": [],
            "all_q_source_csr_covered": False,
            "all_q_symbolic_covered": False,
            "all_q_fresh_factor_probe_covered": False,
            "all_q_factors_simultaneously_resident": False,
            "all_q_factors_retained_simultaneously": False,
            "all_q_factor_objects_live_simultaneously": False,
            "all_q_factors_reused": False,
            "all_q_numeric_factors_strict_true_residual_passed": False,
            "solve_q_coverage": [],
            "all_q_solve_coverage": False,
            "q_rhs_solve_counts": {str(q): 0 for q in range(self.nq)},
            "q_rhs_mat_solve_invoked_counts": {str(q): 0 for q in range(self.nq)},
            "max_simultaneous_factors": 0,
            "max_simultaneous_matrices": 0,
            "factors_live_count_current": 0,
            "matrices_live_count_current": 0,
            "symbolic_build_count": 0,
            "numeric_factor_build_attempt_count": 0,
            "numeric_factor_build_count": 0,
            "cache_miss_count": 0,
            "cache_hit_count": 0,
            "eviction_count": 0,
            "factor_probe_mat_solve_count": 0,
            "factor_probe_mat_solve_completed_count": 0,
            "factor_probe_vec_cleanup_failures": [],
            "factor_probe_vec_cleanup_owner_count": 0,
            "rhs_mat_solve_count_by_category": {
                "pc_initial_rhs_mat_solve_count": 0,
                "pc_augmentation_rhs_mat_solve_count": 0,
                "startup_rhs_mat_solve_count": 0,
                "other_validation_rhs_mat_solve_count": 0,
            },
            "mat_solve_invoked_count_by_category": {
                "pc_initial_rhs_mat_solve_count": 0,
                "pc_augmentation_rhs_mat_solve_count": 0,
                "startup_rhs_mat_solve_count": 0,
                "other_validation_rhs_mat_solve_count": 0,
                "factor_probe_mat_solve_count": 0,
            },
            "mat_solve_completed_count_by_category": {
                "pc_initial_rhs_mat_solve_count": 0,
                "pc_augmentation_rhs_mat_solve_count": 0,
                "startup_rhs_mat_solve_count": 0,
                "other_validation_rhs_mat_solve_count": 0,
                "factor_probe_mat_solve_count": 0,
            },
            "mat_solve_failed_count_by_category": {
                "pc_initial_rhs_mat_solve_count": 0,
                "pc_augmentation_rhs_mat_solve_count": 0,
                "startup_rhs_mat_solve_count": 0,
                "other_validation_rhs_mat_solve_count": 0,
                "factor_probe_mat_solve_count": 0,
            },
            "backend_mat_solve_invoked_total": 0,
            "backend_mat_solve_completed_total": 0,
            "backend_mat_solve_failed_total": 0,
            "factor_tests": [],
            "factor_inputs": [],
            "symbolic_reports_by_q": {},
            "factor_build_history": [],
            "all_q_factors_reused_semantics": (
                "false: the one-q policy rebuilds each factor after eviction"
            ),
            "native_memory_source": "MUMPS INFOG(19/22), raw and upper-bound decoded",
            "native_factor_entries_source": "MUMPS INFOG(9), negative million-entry encoding only",
        }

        try:
            self._retain_and_validate_inputs(matrices)
            self.audit["input_q_coverage"] = sorted(self.csr_matrices)
            self.audit["all_q_source_csr_covered"] = set(self.csr_matrices) == required_q
            for q in range(self.nq):
                self._symbolic_preflight_one_q(q)
                self._evict_slot(reason="bounded_symbolic_complete")
                next_q = q + 1 if q + 1 < self.nq else None
                self._sample_after_eviction(q, next_q=next_q)
            self.audit["all_q_symbolic_covered"] = (
                set(self._symbolic_estimates) == required_q
                and set(self._symbolic_reports) == required_q
                and not self.factors
                and not self.matrices
            )
            self._require_one_q_coverage_gate()
            self._update_total_mat_solve_count()
            self.audit["setup_seconds"] = perf_counter() - self._setup_started
        except BaseException:
            try:
                self.destroy()
            except BaseException as cleanup_error:
                # Keep the still-live backend reachable from the propagated
                # error so callers cannot mistake failed destroy for release.
                cleanup_error.one_q_backend = self
                raise
            raise

    def _retain_and_validate_inputs(self, matrices: Mapping[int, sparse.spmatrix]) -> None:
        PETSc = self.PETSc
        for q in range(self.nq):
            source = matrices[q]
            caller_hash = _sparse_content_sha256(source)
            if (
                not sparse.isspmatrix_csr(source)
                or not source.has_canonical_format
                or not source.has_sorted_indices
            ):
                raise ValueError(
                    f"V19 q={q} source must be canonical sorted CSR before factor lifecycle setup"
                )
            # The formal q builder owns this canonical CSR. Share its backing
            # and freeze the arrays so refactors do not retain a second payload.
            csr = source
            n = self.row_counts[q]
            if not csr.has_canonical_format or not csr.has_sorted_indices:
                raise ValueError(f"q={q} CSR must be canonical and sorted")
            if csr.shape != (n, n):
                raise ValueError(f"q={q} matrix shape {csr.shape} != {(n, n)}")
            if (
                csr.dtype != np.dtype(np.complex128)
                or not np.isfinite(csr.data).all()
                or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128)
            ):
                raise ValueError("ONE_Q_REFACTOR_V19 requires finite complex128 CSR and PETSc")
            csr.data.flags.writeable = False
            csr.indices.flags.writeable = False
            csr.indptr.flags.writeable = False
            int_facts = _petsc_csr_int_preflight(
                csr.shape, csr.nnz, csr.indptr, csr.indices, PETSc.IntType
            )
            csr_hash = _sparse_content_sha256(csr)
            self.source_matrices[q] = source
            self.csr_matrices[q] = csr
            self._input_bindings[q] = {
                "caller_input_sha256_before": caller_hash,
                "factor_csr_sha256_before": csr_hash,
            }
            self.event("task40_v19_one_q_input_identity", {
                "q": q,
                "shape": list(csr.shape),
                "nnz": int(csr.nnz),
                "csr_payload_bytes": _payload_bytes(csr),
                "petsc_int_preflight": int_facts,
                **self._input_bindings[q],
                "canonicalization_copy": False,
                "source_and_retained_csr_shared_backing": csr is source,
                "retained_csr_arrays_write_protected": True,
            })
    def _symbolic_preflight_one_q(self, q: int) -> None:
        csr = self.csr_matrices[q]
        matrix_payload, conversion = self._matrix_payload_and_conversion_bytes(q)
        symbolic_guard = max(
            self._FIXED_HEADROOM_BYTES,
            self._SYMBOLIC_GUARD_MULTIPLIER * int(_payload_bytes(csr)),
        )
        self._admission(
            q,
            "symbolic_admission",
            symbolic_guard=symbolic_guard,
            matrix_payload=matrix_payload,
            conversion_workspace=conversion,
        )
        matrix = factor = None
        try:
            matrix, factor, conversion, conversion_seconds = self._create_slot(q)
            symbolic_started = perf_counter()
            factor.symbolic(matrix)
            elapsed = perf_counter() - symbolic_started
            self.audit["symbolic_build_count"] += 1
            self._assert_input_identity(q, "after_v19_symbolic_preflight")
            info = factor.info(extra_indices=(16, 17, 22, 29), include_local=True)
            estimate = self._symbolic_estimate(q, info)
            report = {
                "q": q,
                "shape": list(csr.shape),
                "nnz": int(csr.nnz),
                "caller_input_sha256": self._input_bindings[q]["caller_input_sha256_before"],
                "factor_csr_sha256": self._input_bindings[q]["factor_csr_sha256_before"],
                "symbolic_elapsed_seconds": float(elapsed),
                "symbolic_estimate_bytes_from_INFOG16_17": estimate,
                "raw_mumps_info": info,
                "native_metrics": _mumps_native_evidence(info, numeric_complete=False),
                "petsc_matrix_info": _petsc_matrix_info(matrix),
                "csr_to_petsc_conversion_workspace_peak_bytes": int(conversion),
                "csr_to_petsc_conversion_seconds": float(conversion_seconds),
                "factor_or_matrix_live_count_during_symbolic": 1,
            }
            self._symbolic_estimates[q] = estimate
            self._symbolic_reports[q] = report
            self.audit["symbolic_reports_by_q"][str(q)] = report
            self.event("task40_v19_one_q_symbolic_q_complete", report)
            self._admission(
                q,
                "symbolic_complete",
                factor_reserve=estimate,
            )
        except BaseException:
            self._evict_slot(reason="symbolic_exception")
            raise




    def _assert_input_identity(self, q: int, stage: str) -> None:
        binding = self._input_bindings[q]
        if _sparse_content_sha256(self.source_matrices[q]) != binding["caller_input_sha256_before"]:
            raise RuntimeError(f"q={q} caller sparse input changed during {stage}")
        if _sparse_content_sha256(self.csr_matrices[q]) != binding["factor_csr_sha256_before"]:
            raise RuntimeError(f"q={q} retained factor CSR changed during {stage}")


    def _resident_factor_evidence(self) -> dict[str, Any]:
        result = {}
        for q, factor in sorted(self.factors.items()):
            if getattr(factor, "numeric_calls", 0) != 1:
                continue
            raw = factor.info(extra_indices=(9, 19, 22, 29), include_local=True)
            result[str(q)] = _mumps_native_evidence(raw, numeric_complete=True)
        return result














    def _sample_after_eviction(self, evicted_q: int, *, next_q: int | None) -> None:
        if self.factors or self.matrices:
            raise RuntimeError("symbolic lifecycle advanced before successful destroy")
        if next_q is None:
            return
        payload, conversion = self._matrix_payload_and_conversion_bytes(next_q)
        guard = max(
            self._FIXED_HEADROOM_BYTES,
            self._SYMBOLIC_GUARD_MULTIPLIER * _payload_bytes(self.csr_matrices[next_q]),
        )
        self._admission(
            next_q,
            "post_eviction_next_symbolic_admission",
            symbolic_guard=guard,
            matrix_payload=payload,
            conversion_workspace=conversion,
        )
        self.event("task40_v19_one_q_post_destroy_sample", {
            "evicted_q": int(evicted_q), "next_q": int(next_q),
            "factor_live_count": 0, "matrix_live_count": 0,
            "resource_admission_after_destroy": True,
        })






    def _update_total_mat_solve_count(self) -> None:
        invoked = self.audit["mat_solve_invoked_count_by_category"]
        completed = self.audit["mat_solve_completed_count_by_category"]
        failed = self.audit["mat_solve_failed_count_by_category"]
        self.audit["rhs_mat_solve_count"] = int(sum(
            self.audit["rhs_mat_solve_count_by_category"].values()
        ))
        self.audit["calls"] = int(self.calls)
        self.audit["actual_backend_mat_solve_total"] = int(
            self.audit["backend_mat_solve_invoked_total"]
        )
        self.audit["mat_solve_count_by_disjoint_category"] = {
            **{key: int(value) for key, value in invoked.items()},
        }
        self.audit["mat_solve_total_identity_passed"] = bool(
            self.audit["backend_mat_solve_invoked_total"] == sum(invoked.values())
            and self.audit["backend_mat_solve_completed_total"] == sum(completed.values())
            and self.audit["backend_mat_solve_failed_total"] == sum(failed.values())
            and self.audit["backend_mat_solve_invoked_total"]
            == self.audit["backend_mat_solve_completed_total"]
            + self.audit["backend_mat_solve_failed_total"]
            and self.audit["rhs_mat_solve_count"] == self.calls
        )

    def _record_mat_solve_invocation(self, category: str, *, q: int | None = None) -> None:
        counts = self.audit["mat_solve_invoked_count_by_category"]
        if category not in counts:
            raise ValueError(f"unknown backend MatSolve category: {category!r}")
        counts[category] += 1
        self.audit["backend_mat_solve_invoked_total"] += 1
        if category == "factor_probe_mat_solve_count":
            self.audit["factor_probe_mat_solve_count"] += 1
        elif q is not None:
            self.audit["q_rhs_mat_solve_invoked_counts"][str(q)] += 1
        self._update_total_mat_solve_count()

    def _record_mat_solve_completion(self, category: str, *, q: int | None = None) -> None:
        counts = self.audit["mat_solve_completed_count_by_category"]
        if category not in counts:
            raise ValueError(f"unknown backend MatSolve category: {category!r}")
        counts[category] += 1
        self.audit["backend_mat_solve_completed_total"] += 1
        if category == "factor_probe_mat_solve_count":
            self.audit["factor_probe_mat_solve_completed_count"] += 1
        else:
            self.audit["rhs_mat_solve_count_by_category"][category] += 1
            self.calls += 1
            if q is not None:
                self.audit["q_rhs_solve_counts"][str(q)] += 1
                self._solved_qs.add(q)
                self.audit["solve_q_coverage"] = sorted(self._solved_qs)
                self.audit["all_q_solve_coverage"] = self._solved_qs == set(range(self.nq))
        self._update_total_mat_solve_count()

    def _record_mat_solve_failure(self, category: str) -> None:
        counts = self.audit["mat_solve_failed_count_by_category"]
        if category not in counts:
            raise ValueError(f"unknown backend MatSolve category: {category!r}")
        counts[category] += 1
        self.audit["backend_mat_solve_failed_total"] += 1
        self._update_total_mat_solve_count()


    def _resident_q(self) -> int | None:
        return next(iter(self.factors), None)

    def solve(
        self,
        q: int,
        rhs: np.ndarray,
        *,
        category: str = "other_validation_rhs_mat_solve_count",
    ) -> np.ndarray:
        categories = self.audit["rhs_mat_solve_count_by_category"]
        if category not in categories:
            raise ValueError(f"unknown V19 MatSolve RHS category: {category!r}")
        if self.destroyed:
            raise RuntimeError("one-q factor backend has been destroyed")
        if type(q) is not int or q not in range(self.nq):
            raise ValueError(f"actual q branch index 0..{self.nq - 1} is required")
        values = np.asarray(rhs, dtype=np.complex128)
        if values.shape != (self.row_counts[q],) or not np.isfinite(values).all():
            raise ValueError("complete finite q-branch RHS required")
        try:
            if self._resident_q() != q or set(self.matrices) != {q}:
                if self.factors or self.matrices:
                    self._evict_slot(reason=f"q_switch_to_{q}")
            self._ensure_factor(q, rhs_category=category)
        except BaseException:
            if self.factors or self.matrices:
                try:
                    self._evict_slot(reason=f"q{q}_factor_admission_failed")
                except BaseException as cleanup_error:
                    cleanup_error.one_q_backend = self
                    raise
            raise
        try:
            PETSc = self.PETSc
            b = x = None
            try:
                b = PETSc.Vec().createSeq(len(values), comm=PETSc.COMM_SELF)
                x = b.duplicate()
                b.array[:] = values
                self._record_mat_solve_invocation(category, q=q)
                try:
                    self.factors[q].solve_repeated(b, x)
                except BaseException:
                    self._record_mat_solve_failure(category)
                    raise
                self._record_mat_solve_completion(category, q=q)
                solution = x.array.copy()
            finally:
                if x is not None:
                    x.destroy()
                if b is not None:
                    b.destroy()
        except BaseException:
            try:
                self._evict_slot(reason=f"rhs_solve_failed_q{q}")
            except BaseException as cleanup_error:
                cleanup_error.one_q_backend = self
                raise
            raise
        return solution

    def _ensure_factor(self, q: int, *, rhs_category: str) -> None:
        if self.destroyed:
            raise RuntimeError("one-q factor backend has been destroyed")
        if self._resident_q() == q and set(self.matrices) == {q}:
            self.audit["cache_hit_count"] += 1
            return
        if self.factors or self.matrices:
            raise RuntimeError("a different q still owns the one-q slot")
        self._assert_input_identity(q, "before_v19_factor_cache_miss")
        matrix_payload, conversion = self._matrix_payload_and_conversion_bytes(q)
        estimate = int(self._symbolic_estimates[q])
        self.audit["cache_miss_count"] += 1
        self._admission(
            q,
            "factor_cache_miss_admission_v19",
            factor_reserve=estimate,
            matrix_payload=matrix_payload,
            conversion_workspace=conversion,
        )
        build_index = int(self.audit["numeric_factor_build_attempt_count"])
        build_row: dict[str, Any] = {
            "build_index": build_index,
            "q": q,
            "rhs_category_context": rhs_category,
            "source_csr_sha256": self._input_bindings[q]["factor_csr_sha256_before"],
            "preflight_symbolic_estimate_bytes": estimate,
            "symbolic_elapsed_seconds": None,
            "numeric_elapsed_seconds": None,
            "csr_to_petsc_conversion_workspace_bytes": None,
            "csr_to_petsc_conversion_seconds": None,
            "factor_probe_elapsed_seconds": None,
            "cache_miss_parent_seconds": None,
            "factor_probe_mat_solve_count": 0,
            "probe_true_residual_relative": None,
            "factor_probe_passed": False,
        }
        self.audit["factor_build_history"].append(build_row)
        cache_miss_started = perf_counter()
        try:
            matrix, factor, conversion, conversion_seconds = self._create_slot(q)
            build_row["csr_to_petsc_conversion_workspace_bytes"] = int(conversion)
            build_row["csr_to_petsc_conversion_seconds"] = float(conversion_seconds)
            symbolic_started = perf_counter()
            factor.symbolic(matrix)
            symbolic_elapsed = perf_counter() - symbolic_started
            self.audit["symbolic_build_count"] += 1
            build_row["symbolic_elapsed_seconds"] = float(symbolic_elapsed)
            symbolic_info = factor.info(extra_indices=(16, 17, 22, 29), include_local=True)
            estimate = max(estimate, self._symbolic_estimate(q, symbolic_info))
            build_row["fresh_symbolic_estimate_bytes"] = estimate
            self._assert_input_identity(q, "after_v19_fresh_symbolic")
            self._admission(q, "fresh_symbolic_before_numeric_gate_v19", factor_reserve=estimate)
            self.audit["numeric_factor_build_attempt_count"] += 1
            numeric_started = perf_counter()
            factor.numeric(matrix)
            numeric_elapsed = perf_counter() - numeric_started
            self.audit["numeric_factor_build_count"] += 1
            build_row["numeric_elapsed_seconds"] = float(numeric_elapsed)
            self._assert_input_identity(q, "after_v19_numeric_factor")
            if factor.get_icntl(10) != 0 or factor.get_icntl(35) != 0:
                raise ValueError("exact MUMPS refinement/storage controls changed")
            numeric_info = factor.info(extra_indices=(16, 17, 22, 29), include_local=True)
            native = _mumps_native_evidence(numeric_info, numeric_complete=True)
            self.event("task40_v19_one_q_numeric_q_complete", {
                "q": q,
                "shape": list(self.csr_matrices[q].shape),
                "nnz": int(self.csr_matrices[q].nnz),
                "fresh_symbolic_elapsed_seconds": float(symbolic_elapsed),
                "numeric_elapsed_seconds": float(numeric_elapsed),
                "raw_mumps_info": numeric_info,
                "native_metrics": native,
                "factor_lifecycle_strategy": ONE_Q_REFACTOR_V19,
                "max_live_factor_count": self._max_simultaneous_factors,
                "max_live_matrix_count": self._max_simultaneous_matrices,
            })
            self._admission(q, "numeric_factor_resident_gate_v19")
            n = self.row_counts[q]
            probe_rhs = np.cos(.23 * np.arange(n)) + 1j * np.sin(.37 * np.arange(n))
            probe_started = perf_counter()
            self._solve_probe(q, probe_rhs)
            probe_elapsed = perf_counter() - probe_started
            build_row["factor_probe_elapsed_seconds"] = float(probe_elapsed)
            build_row["factor_probe_mat_solve_count"] = 1
            self._assert_input_identity(q, "after_v19_factor_probe")
            probe_solution = self._last_probe_solution
            residual = float(
                np.linalg.norm(self.csr_matrices[q] @ probe_solution - probe_rhs)
                / np.linalg.norm(probe_rhs)
            )
            del probe_solution
            del self._last_probe_solution
            passed = bool(np.isfinite(residual) and residual <= self.factor_probe_limit)
            build_row["probe_true_residual_relative"] = residual
            build_row["factor_probe_passed"] = passed
            test = {
                "q": q, "rows": int(n), "relative_true_residual": residual,
                "strict_limit": 1.0e-10, "strict_passed": passed,
                "limit": 1.0e-10, "admission_passed": passed,
                "factor_lifecycle_strategy": ONE_Q_REFACTOR_V19,
                "symbolic_seconds": float(symbolic_elapsed),
                "numeric_seconds": float(numeric_elapsed),
                "factor_probe_elapsed_seconds": float(probe_elapsed),
                "process_tree_rss_bytes": None,
            }
            self.audit["factor_tests"].append(test)
            self.event("task40_v19_one_q_numeric_q_probe_complete", {
                **test, "native_metrics": native, "raw_mumps_info": numeric_info,
                "probe_rhs_category": "factor_probe_mat_solve_count",
            })
            if not passed:
                raise ValueError(f"q={q} fresh V19 factor probe failed: {residual} > 1e-10")
            self._passed_factor_qs.add(q)
            self.audit["all_q_fresh_factor_probe_covered"] = self._passed_factor_qs == set(range(self.nq))
            self.audit["all_q_numeric_factors_strict_true_residual_passed"] = (
                self.audit["all_q_fresh_factor_probe_covered"]
            )
            binding = self._input_bindings[q]
            binding["caller_input_sha256_after"] = _sparse_content_sha256(self.source_matrices[q])
            binding["factor_csr_sha256_after"] = _sparse_content_sha256(self.csr_matrices[q])
            self.audit["factor_inputs"].append({
                "build_index": build_index, "q": q,
                "shape": list(self.csr_matrices[q].shape),
                "nnz": int(self.csr_matrices[q].nnz),
                **binding, "input_identity_unchanged": True,
                "symbolic_estimate_bytes_from_INFOG16_17": int(estimate),
                "native_memory_observation": native["memory_observation"],
                "native_allocated_bytes_upper": native["INFOG_19_allocated_bytes_upper"],
                "native_used_bytes_upper": native["INFOG_22_used_bytes_upper"],
                "native_factor_entries": native["INFOG_9_corrected_entries_if_negative"],
                "mumps_info_raw": numeric_info,
                "process_tree_rss_bytes": None,
                "factor_and_matrix_live_during_probe": True,
            })
            build_row["cache_miss_parent_seconds"] = float(
                perf_counter() - cache_miss_started
            )
        except BaseException:
            try:
                self._evict_slot(reason=f"factor_build_or_probe_failed_q{q}")
            except BaseException as cleanup_error:
                build_row["cache_miss_parent_seconds"] = float(
                    perf_counter() - cache_miss_started
                )
                cleanup_error.one_q_backend = self
                raise
            build_row["cache_miss_parent_seconds"] = float(
                perf_counter() - cache_miss_started
            )
            raise

    def _solve_probe(self, q: int, rhs: np.ndarray) -> None:
        PETSc = self.PETSc
        b = x = None
        try:
            b = PETSc.Vec()
            b.createSeq(len(rhs), comm=PETSc.COMM_SELF)
            x = b.duplicate()
            b.array[:] = rhs
            category = "factor_probe_mat_solve_count"
            self._record_mat_solve_invocation(category)
            try:
                self.factors[q].solve(b, x)
            except BaseException:
                self._record_mat_solve_failure(category)
                raise
            self._record_mat_solve_completion(category)
            self._last_probe_solution = x.array.copy()
        except BaseException as primary_error:
            cleanup_errors = self._destroy_probe_vectors(x=x, b=b)
            if cleanup_errors:
                primary_error.probe_cleanup_errors = tuple(cleanup_errors)
                primary_error.one_q_backend = self
                primary_error.add_note(
                    "one or more probe Vec owners could not be confirmed destroyed; "
                    "the backend retains them and will refuse another q slot"
                )
            raise
        else:
            cleanup_errors = self._destroy_probe_vectors(x=x, b=b)
            if cleanup_errors:
                error = RuntimeError(
                    "failed to destroy a probe Vec; its native owner is retained and "
                    "no new q slot may be created"
                )
                error.probe_cleanup_errors = tuple(cleanup_errors)
                error.one_q_backend = self
                raise error from cleanup_errors[0]

    def _destroy_probe_vectors(self, *, x: Any, b: Any) -> list[BaseException]:
        errors: list[BaseException] = []
        for label, vector in (("x", x), ("b", b)):
            if vector is None:
                continue
            try:
                vector.destroy()
            except BaseException as exc:
                errors.append(exc)
                self._probe_cleanup_owners.append((label, vector, exc))
                self.audit["factor_probe_vec_cleanup_failures"].append({
                    "vector": label,
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "owner_retained": True,
                })
        self.audit["factor_probe_vec_cleanup_owner_count"] = len(
            self._probe_cleanup_owners
        )
        return errors

    def _resource_sample(self, *, q: int, stage: str, reason: str) -> dict[str, Any]:
        facts = {
            "factor_lifecycle_strategy": ONE_Q_REFACTOR_V19,
            "resource_sample_only": True,
            "q": int(q),
            "sample_stage": str(stage),
            "reason": str(reason),
            "factor_q_indices": sorted(self.factors),
            "matrix_q_indices": sorted(self.matrices),
            "factors_live_count_current": len(self.factors),
            "matrices_live_count_current": len(self.matrices),
            "current_work_arrays_already_live": True,
        }
        result = self.gate(f"one_q_resource_sample_v19_{stage}", facts)
        return {**facts, **(dict(result) if isinstance(result, Mapping) else {"gate_return": result})}

    def _evict_slot(self, *, reason: str) -> None:
        if len(self.factors) > 1 or len(self.matrices) > 1:
            raise RuntimeError("one-q slot inventory is already inconsistent")
        resident_qs = sorted(set(self.factors).union(self.matrices))
        if not resident_qs:
            self._note_live_counts()
            return
        q = resident_qs[0]
        sample_errors = []
        try:
            before_sample = self._resource_sample(q=q, stage="before_destroy", reason=reason)
        except BaseException as exc:
            sample_errors.append(exc)
            before_sample = {
                "sample_failed": True,
                "sample_error_type": type(exc).__name__,
                "sample_error_message": str(exc),
            }
        errors = []
        for q in list(self.factors):
            factor = self.factors[q]
            try:
                destroy = getattr(factor, "destroy", None)
                if not callable(destroy):
                    raise RuntimeError("MUMPS factor has no callable destroy method")
                destroy()
            except BaseException as exc:
                self.audit["last_destroy_failure"] = {
                    "kind": "factor", "q": q, "reason": reason,
                    "type": type(exc).__name__, "message": str(exc), "still_live": True,
                }
                errors.append(exc)
            else:
                del self.factors[q]
                self.audit["eviction_count"] += 1
                del factor
                gc.collect()
        if not errors:
            for q in list(self.matrices):
                matrix = self.matrices[q]
                try:
                    matrix.destroy()
                except BaseException as exc:
                    self.audit["last_destroy_failure"] = {
                        "kind": "matrix", "q": q, "reason": reason,
                        "type": type(exc).__name__, "message": str(exc), "still_live": True,
                    }
                    errors.append(exc)
                else:
                    del self.matrices[q]
                    del matrix
                    gc.collect()
        self._note_live_counts()
        try:
            after_sample = self._resource_sample(q=q, stage="after_destroy", reason=reason)
        except BaseException as exc:
            sample_errors.append(exc)
            after_sample = {
                "sample_failed": True,
                "sample_error_type": type(exc).__name__,
                "sample_error_message": str(exc),
            }
        succeeded = not errors and not self.factors and not self.matrices
        if getattr(self, "_ever_had_slot", False):
            self.event("task40_v19_one_q_slot_destroyed", {
                "reason": str(reason),
                "q": int(q),
                "factor_live_count_after_destroy": len(self.factors),
                "matrix_live_count_after_destroy": len(self.matrices),
                "destroy_succeeded_before_slot_reuse": succeeded,
                "resource_sample_before_destroy": before_sample,
                "resource_sample_after_destroy": after_sample,
            })
        if errors:
            kind = "factor" if self.factors else "PETSc input matrix"
            raise RuntimeError(f"failed to destroy the live q {kind}; no new q may be created") from errors[0]
        if sample_errors:
            raise RuntimeError(
                "q slot was destroyed, but required before/after resource sampling failed; "
                "no next q may be created"
            ) from sample_errors[0]
        self._ever_had_slot = False

    def _note_live_counts(self) -> None:
        factor_count, matrix_count = len(self.factors), len(self.matrices)
        self._max_simultaneous_factors = max(self._max_simultaneous_factors, factor_count)
        self._max_simultaneous_matrices = max(self._max_simultaneous_matrices, matrix_count)
        self.audit["factors_live_count_current"] = factor_count
        self.audit["matrices_live_count_current"] = matrix_count
        self.audit["max_simultaneous_factors"] = self._max_simultaneous_factors
        self.audit["max_simultaneous_matrices"] = self._max_simultaneous_matrices
        if factor_count > 1 or matrix_count > 1:
            raise RuntimeError("ONE_Q_REFACTOR_V19 exceeded its single live matrix/factor slot")

    def _create_slot(self, q: int) -> tuple[Any, Any, int, float]:
        if self._probe_cleanup_owners:
            label, _owner, owner_error = self._probe_cleanup_owners[0]
            error = RuntimeError(
                f"cannot create q={q} factor slot while a probe Vec {label} "
                "has an unconfirmed native destroy"
            )
            error.one_q_backend = self
            raise error from owner_error
        csr = self.csr_matrices[q]
        PETSc = self.PETSc
        conversion_started = perf_counter()
        indptr = np.asarray(csr.indptr, dtype=PETSc.IntType).copy()
        indices = np.asarray(csr.indices, dtype=PETSc.IntType).copy()
        values = np.asarray(csr.data, dtype=PETSc.ScalarType).copy()
        conversion_bytes = int(indptr.nbytes + indices.nbytes + values.nbytes)
        matrix = PETSc.Mat().createAIJ(size=csr.shape, csr=(indptr, indices, values), comm=PETSc.COMM_SELF)
        conversion_seconds = perf_counter() - conversion_started
        self.matrices[q] = matrix
        self._ever_had_slot = True
        self._note_live_counts()
        try:
            matrix.assemble()
            factor = self._factor_factory(matrix)
            self.factors[q] = factor
            self._note_live_counts()
        finally:
            del indptr, indices, values
        return matrix, self.factors[q], conversion_bytes, float(conversion_seconds)

    def _matrix_payload_and_conversion_bytes(self, q: int) -> tuple[int, int]:
        csr = self.csr_matrices[q]
        index_itemsize = np.dtype(self.PETSc.IntType).itemsize
        value_itemsize = np.dtype(self.PETSc.ScalarType).itemsize
        payload = int(
            (csr.indptr.size + csr.indices.size) * index_itemsize
            + csr.data.size * value_itemsize
        )
        return payload, payload

    def _admission(self, q: int, stage: str, *, symbolic_guard: int = 0,
                   factor_reserve: int = 0, matrix_payload: int = 0,
                   conversion_workspace: int = 0) -> dict[str, Any]:
        future = self._static_future_reserve()
        components = {
            "persistent_pending_transform_inverse_payload_bytes": int(future["future_inverse_payload_bytes"]),
            "selected_maximum_co_resident_phase_bytes": int(future["selected_future_nonfactor_co_resident_phase_bytes"]),
            "one_q_symbolic_guard_bytes": int(symbolic_guard),
            "one_q_numeric_factor_reserve_bytes": int(factor_reserve),
        }
        facts = {
            "factor_lifecycle_strategy": ONE_Q_REFACTOR_V19,
            "q": int(q), "stage": str(stage),
            "additional_payload_bytes": int(matrix_payload),
            "workspace_bytes": int(conversion_workspace),
            "future_reserve_components": components,
            "future_co_resident_reserve_bytes": sum(components.values()),
            "current_work_arrays_already_live": True,
            "current_work_array_scope": (
                "allocation callback samples current process-tree/cgroup RSS; during solve this "
                "includes the folded RHS, native FE/port vectors and active PC state"
            ),
            "all_q_source_csr_retained": True,
            "all_q_symbolic_covered_before_numeric": bool(self.audit.get("all_q_symbolic_covered")),
            "numeric_factors_to_be_retained_simultaneously": 1,
            **future,
        }
        self.event("task40_v19_one_q_admission_request", facts)
        admitted = self.gate(f"one_q_{stage}_v19", facts)
        return dict(admitted) if isinstance(admitted, Mapping) else {"gate_return": admitted}

    def _static_future_reserve(self) -> dict[str, Any]:
        rows = int(sum(self.row_counts))
        krylov_count, ksp_count = 2 * (32 + 1), 6
        future_krylov = rows * (krylov_count + ksp_count) * np.dtype(np.complex128).itemsize
        output_rows = int(self.full_storage_rows or 0)
        output_inventory = full_p6_pre_release_output_inventory(output_rows)
        future_output = int(output_inventory["pre_release_peak_bytes"])
        bank = self.transform_bank.future_inverse_reserve() if self.transform_bank is not None else {
            "future_unique_inverse_payload_bytes": 0,
            "future_single_inverse_workspace_bytes": 0,
            "future_unique_inverse_template_count": 0,
        }
        legacy = {
            str(label): borrower.future_legacy_inverse_reserve()
            for label, borrower in self.inverse_borrowers.items()
        }
        inverse_payload = int(bank["future_unique_inverse_payload_bytes"]) + sum(
            int(row["future_legacy_inverse_payload_bytes"]) for row in legacy.values()
        )
        inverse_workspace = max(
            [int(bank["future_single_inverse_workspace_bytes"])]
            + [int(row["future_legacy_single_inverse_workspace_bytes"]) for row in legacy.values()]
        )
        ksp_phase = future_krylov + inverse_workspace
        recovery_phase = future_output + inverse_workspace
        return {
            "retained_vector_rows": rows,
            "krylov_basis_vector_count": krylov_count,
            "ksp_workspace_vector_count": ksp_count,
            "future_krylov_and_vector_bytes": int(future_krylov),
            "full_storage_rows_for_recovery": output_rows,
            "future_full_p6_recovery_output_bytes": future_output,
            "pre_release_recovery_output_inventory": {
                **output_inventory,
                "actual_target_and_reference_full_rows_match_required": self.target_reference_rows_match,
            },
            "future_inverse_payload_bytes": inverse_payload,
            "future_inverse_single_operation_workspace_bytes": inverse_workspace,
            "future_bank_inverse_reserve": bank,
            "future_legacy_inverse_reserves_by_collection": legacy,
            "selected_future_nonfactor_co_resident_phase": (
                "KSP_with_inverse_workspace" if ksp_phase >= recovery_phase
                else "pre_release_full_p6_recovery_output_with_inverse_workspace"
            ),
            "selected_future_nonfactor_co_resident_phase_bytes": int(max(ksp_phase, recovery_phase)),
            "future_nonfactor_co_resident_reserve_bytes": int(
                inverse_payload + max(ksp_phase, recovery_phase)
            ),
        }

    def _symbolic_estimate(self, q: int, info: Mapping[str, Any]) -> int:
        infog = info.get("infog")
        if not isinstance(infog, Mapping):
            raise RuntimeError(f"q={q} symbolic MUMPS INFOG is unavailable")
        info16, info17 = infog.get("16"), infog.get("17")
        if type(info16) is not int or type(info17) is not int or min(info16, info17) < 0 or info16 != info17:
            raise RuntimeError(f"q={q} symbolic INFOG(16/17) estimates are unsupported")
        return int(1_000_000 * (1 + max(info16, info17)))

    def _require_one_q_coverage_gate(self) -> None:
        required = set(range(self.nq))
        if (
            set(self._symbolic_estimates) != required
            or set(self._symbolic_reports) != required
            or not self.audit["all_q_source_csr_covered"]
            or self.factors
            or self.matrices
        ):
            raise RuntimeError("ONE_Q_REFACTOR_V19 symbolic coverage is incomplete or retains a slot")
        self._admission(0, "symbolic_coverage_gate_v19", factor_reserve=max(self._symbolic_estimates.values()))
        self.audit["all_q_symbolic_covered"] = True
        self.event("task40_v19_one_q_symbolic_coverage_complete", {
            "q_symbolic_estimates_bytes": {str(q): self._symbolic_estimates[q] for q in range(self.nq)},
            "all_q_symbolic_covered": True,
            "numeric_factors_to_be_retained_simultaneously": 1,
            "all_q_source_csr_covered": True,
            "all_symbolic_objects_destroyed_before_next_q": True,
        })

    def capabilities(self) -> dict[str, Any]:
        return {
            "factor_lifecycle_strategy": ONE_Q_REFACTOR_V19,
            "input_q_coverage": sorted(self.csr_matrices),
            "all_q_source_csr_covered": set(self.csr_matrices) == set(range(self.nq)),
            "solve_q_coverage": sorted(self._solved_qs),
            "all_q_solve_coverage": self._solved_qs == set(range(self.nq)),
            "all_q_factors_simultaneously_resident": False,
            "all_q_factors_retained_simultaneously": False,
            "max_live_factors": self._max_simultaneous_factors,
            "max_live_matrices": self._max_simultaneous_matrices,
            "all_q_fresh_factor_probe_covered": self.audit["all_q_fresh_factor_probe_covered"],
            "all_q_factors_reused": False,
        }

    def verify_all_input_identities(self, *, stage: str = "final") -> dict[int, bool]:
        if self.destroyed:
            raise RuntimeError("cannot verify q CSR identity after cleanup")
        verified = {}
        for q in range(self.nq):
            binding = self._input_bindings[q]
            if _sparse_content_sha256(self.source_matrices[q]) != binding["caller_input_sha256_before"]:
                raise RuntimeError(f"q={q} caller sparse input changed during {stage}")
            if _sparse_content_sha256(self.csr_matrices[q]) != binding["factor_csr_sha256_before"]:
                raise RuntimeError(f"q={q} retained factor CSR changed during {stage}")
            verified[q] = True
        self.audit["final_input_identity_checks"] = {
            "stage": str(stage), "q": sorted(verified),
            "passed": len(verified) == self.nq,
            "identity_scope": "all retained q CSR, including evicted and never-built factors",
        }
        return verified

    def destroy(self) -> None:
        if self.destroyed:
            return
        native_inventory = None
        native_inventory_error = None
        try:
            native_inventory = self._resident_factor_evidence()
        except Exception as exc:
            native_inventory_error = {
                "type": type(exc).__name__,
                "message": str(exc),
                "cleanup_continued": True,
            }
        self.audit["pre_destroy_live_inventory"] = {
            "factor_q_indices": sorted(self.factors),
            "matrix_q_indices": sorted(self.matrices),
            "factor_live_count": len(self.factors),
            "matrix_live_count": len(self.matrices),
            "max_simultaneous_factors": self._max_simultaneous_factors,
            "max_simultaneous_matrices": self._max_simultaneous_matrices,
            "all_q_factors_live": False,
            "current_native_factor_inventory_by_q": native_inventory,
            "native_factor_inventory_error": native_inventory_error,
            "destroy_not_yet_started": True,
        }
        self._evict_slot(reason="backend_close")
        if self._probe_cleanup_owners:
            label, _owner, owner_error = self._probe_cleanup_owners[0]
            error = RuntimeError(
                f"cannot confirm probe Vec {label} destruction; backend close is incomplete"
            )
            error.one_q_backend = self
            raise error from owner_error
        self.destroyed = True
        self.source_matrices.clear()
        self.csr_matrices.clear()
        self._input_bindings.clear()
        self.audit["factors_live_count_current"] = 0
        self.audit["matrices_live_count_current"] = 0
        self.audit["close_succeeded"] = True

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.destroy()
