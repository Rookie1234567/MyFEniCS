"""All-q exact MUMPS factors for the Task40 V10 p6 periodic reference.

The four modal sparse matrices and their factors remain live together. MUMPS
setup uses the project's existing exact backend controls. Native factor
statistics and process-tree RSS remain separate evidence channels.
"""
from __future__ import annotations

from hashlib import sha256
from time import perf_counter
from typing import Callable, Mapping, Sequence

import numpy as np
from scipy import sparse

from .task40_v10_p6_periodic_profile import TASK40_V10_P6_PROFILE


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
    def __init__(self, matrices: Mapping[int, sparse.spmatrix], *,
                 allocation_gate: Callable[[str, Mapping[str, object]], None],
                 event: Callable[[str, Mapping[str, object]], None] | None = None,
                 expected_shapes: Sequence[int] | None = None):
        from petsc4py import PETSc
        from src.runners.physical_p4_cell_condensed_v18 import _factor_factory_for_backend

        self.PETSc = PETSc
        self.event = event or (lambda _name, _facts: None)
        if not callable(allocation_gate):
            raise TypeError("an active process-tree allocation gate is required")
        self.gate = allocation_gate
        self.nq = TASK40_V10_P6_PROFILE.q_count
        self.row_counts = tuple(expected_shapes or TASK40_V10_P6_PROFILE.augmented_rows_per_q)
        if len(self.row_counts) != self.nq or set(matrices) != set(range(self.nq)):
            raise ValueError("all four actual q matrices are required before factorization")
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
            "profile": TASK40_V10_P6_PROFILE.name,
            "all_q_required": list(range(self.nq)),
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
            # Right FGMRES retains V_(m+1) and Z_m; reserve additional full
            # vectors for residual, work, solution, and checkpoint staging.
            retained_vector_count = 2 * (32 + 1) + 6
            future_krylov_bytes = int(
                retained_rows
                * retained_vector_count
                * np.dtype(np.complex128).itemsize
            )
            self.gate("all_q_symbolic_before_any_numeric", {
                "q_symbolic_estimates_bytes": {
                    str(q): symbolic_estimates[q] for q in range(self.nq)
                },
                "all_q_symbolic_estimate_sum_bytes": int(sum(symbolic_estimates.values())),
                "all_four_symbolic_q_completed": set(symbolic_estimates) == set(range(self.nq)),
                "future_retained_krylov_and_vector_bytes": future_krylov_bytes,
                "retained_vector_count_upper_bound": retained_vector_count,
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
                    "sum(actual_per_q_INFOG16_17_estimates)+future_Krylov_vectors+"
                    "128MiB_against_live_RSS_and_finite_campaign_cap"
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
                rhs = np.cos(.23*np.arange(n)) + 1j*np.sin(.37*np.arange(n))
                solution = self._solve_once(q, rhs)
                self._assert_input_identity(q, "after_probe_solve")
                residual = float(np.linalg.norm(csr @ solution-rhs)/np.linalg.norm(rhs))
                test = {
                    "q": q,
                    "rows": n,
                    "relative_true_residual": residual,
                    "limit": 1e-10,
                    "symbolic_seconds": symbolic_seconds,
                    "numeric_seconds": numeric_seconds,
                    "ICNTL_10": factor.get_icntl(10),
                    "ICNTL_35": factor.get_icntl(35),
                }
                self.audit["factor_tests"].append(test)
                if not np.isfinite(residual) or residual > 1e-10:
                    raise ValueError(f"q={q} exact MUMPS true residual failed: {residual}")
                self.gate("after_mumps_numeric_true_residual", {
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
                    "numeric_true_residual_limit": 1e-10,
                    "process_tree_rss_bytes": None,
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
                    "process_tree_rss_bytes": None,
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
                all_four_factors_retained_simultaneously=(
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
                all_four_numeric_factors_true_residual_passed=(
                    {int(row["q"]) for row in self.audit["factor_tests"]}
                    == set(range(self.nq))
                    and all(
                        np.isfinite(float(row["relative_true_residual"]))
                        and float(row["relative_true_residual"]) <= float(row["limit"])
                        for row in self.audit["factor_tests"]
                    )
                ),
                all_four_factor_objects_live_simultaneously=(
                    self._max_simultaneous_factors == self.nq
                ),
                factors_live_count_current=len(self.factors),
                max_simultaneous_factors=self._max_simultaneous_factors,
                factor_fill_bytes=None,
                process_tree_peak_rss_bytes=None,
                factor_factory="physical_p4_cell_condensed_v18._factor_factory_for_backend('exact')",
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
            self.audit["all_four_factor_objects_live_simultaneously"] = True

    def _resident_factor_evidence(self, *, exclude_q: int | None = None) -> dict[str, object]:
        result: dict[str, object] = {}
        for q, factor in sorted(self.factors.items()):
            if q == exclude_q or factor.numeric_calls != 1:
                continue
            raw = factor.info(extra_indices=(22, 29), include_local=True)
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
            raise RuntimeError("all four live p6 q factors are required")
        if type(q) is not int or q not in range(self.nq):
            raise ValueError("actual q branch index 0..3 is required")
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
        # Keep object-liveness historical, but never call a symbolic-only
        # object set a qualified four-q numeric factor set.
        self.audit["all_four_factor_objects_live_simultaneously"] = (
            self._max_simultaneous_factors == self.nq
        )
        if errors:
            raise RuntimeError(f"failed to destroy {len(errors)} PETSc/MUMPS objects") from errors[0]

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.destroy()
