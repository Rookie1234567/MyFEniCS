"""Staged all-y-block inverse of an exactly cell-condensed full-3D reference.

This is a targeted extension of Task040 S2c/S2d, not a new reference-inverse
concept.  The qualified full-FE entity/orientation map is reused.  Only its
trace restriction is transformed here; the existing P4CellCondensedInverse
retains/reduces/recovers every original cell interior and port coupling.

Q is a primal map, Q^H is its variational dual.  Q^-1 is never substituted
for Q^H, nor is raw H(curl)-moment Euclidean unitarity assumed.  Every actual
physical port keeps its own column and normalization, even when n aliases.
No global dense FE/modal matrix, sector projection, or +/-q factor reuse.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from time import perf_counter
from typing import Any, Callable

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu

from src.solvers.task40extra_y_orbit_reference import LIMITS, _relative


SCHEMA = "task40extra.y-orbit-sparse-condensed-reference.v1"
FACTOR_ALLOWANCE_BYTES = 512 * 1024**2
EVIDENCE_RESERVE_BYTES = 128 * 1024**2
TREE_CAP_BYTES = 3 * 1024**3 // 2


def integer_admission(shape, nnz, *, index_dtype, indptr_dtype=None):
    """Reject overflow before a sparse allocation or a narrowing conversion.

    Shape/NNZ are Python integers.  Stored-entry and row-pointer limits matter
    independently of global row count.  In particular int32 qualification of
    this small pilot cannot be extrapolated to target-scale CSR construction.
    """
    shape = tuple(int(v) for v in shape)
    nnz = int(nnz)
    index_dtype = np.dtype(index_dtype)
    indptr_dtype = np.dtype(indptr_dtype if indptr_dtype is not None else index_dtype)
    if len(shape) != 2 or min(shape) < 0 or nnz < 0:
        raise ValueError("invalid sparse dimensions or stored-entry count")
    for name, dtype, maximum in (
        ("indices", index_dtype, max(shape)), ("indptr", indptr_dtype, nnz),
    ):
        if dtype.kind != "i" or maximum > int(np.iinfo(dtype).max):
            raise OverflowError(f"{name} {dtype} cannot represent {maximum}")
    return {"shape": list(shape), "stored_entries_upper": nnz,
            "indices_dtype": str(index_dtype), "indptr_dtype": str(indptr_dtype),
            "indices_bits": index_dtype.itemsize * 8,
            "indptr_bits": indptr_dtype.itemsize * 8,
            "overflow_rejected_before_conversion": True}


def csr_audit(matrix, *, petsc_index_dtype):
    if not sparse.isspmatrix_csr(matrix) or not matrix.has_canonical_format:
        raise ValueError("require an existing canonical CSR; no implicit copy")
    native = integer_admission(matrix.shape, matrix.nnz, index_dtype=matrix.indices.dtype,
                               indptr_dtype=matrix.indptr.dtype)
    abi = integer_admission(matrix.shape, matrix.nnz, index_dtype=petsc_index_dtype)
    if (int(matrix.indptr[-1]) != matrix.nnz or np.any(np.diff(matrix.indptr) < 0)
            or (matrix.nnz and (np.min(matrix.indices) < 0
                               or np.max(matrix.indices) >= matrix.shape[1]))
            or matrix.dtype != np.dtype(np.complex128)
            or not np.isfinite(matrix.data).all()):
        raise ValueError("malformed or nonfinite complex128 CSR")
    return {"actual": native, "qualified_PETSc_IntType": abi,
            "payload_bytes": int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)}


def sparse_hash(matrix):
    """Hash actual CSR buffers without a canonicalization or dense copy."""
    digest = hashlib.sha256()
    digest.update(np.asarray(matrix.shape, dtype="<i8").tobytes())
    for values in (matrix.indptr, matrix.indices, matrix.data):
        digest.update(str(values.dtype).encode() + b"\0")
        digest.update(memoryview(np.ascontiguousarray(values)).cast("B"))
    return digest.hexdigest()


def _gate(gate, name, payload=0, workspace=0, **facts):
    if not callable(gate):
        raise ValueError("a measured aggregate process-tree allocation gate is required")
    gate(name, {"matrix_payload_bytes": int(payload), "workspace_bytes": int(workspace),
                "allocation_semantics": "additional_objects_not_current_resident_RSS", **facts})


def _product_bound(left, right):
    """Conservative support bound from existing sparse graphs, no product yet."""
    if left.shape[1] != right.shape[0]:
        raise ValueError("incompatible sparse product dimensions")
    right_widths = np.diff(right.indptr)
    result = 0
    # Python integer accumulation avoids overflow in a capacity preflight.
    for first, last in zip(left.indptr[:-1], left.indptr[1:], strict=True):
        result += min(right.shape[1], sum(int(right_widths[int(j)])
                                         for j in left.indices[int(first):int(last)]))
    return result


def _product(left, right, *, allocation_gate, name, index_dtype):
    for side, matrix in (("left", left), ("right", right)):
        if not sparse.isspmatrix_csr(matrix):
            payload = matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes
            _gate(allocation_gate, name + "_" + side + "_CSR_conversion", payload, payload)
    left = left.tocsr(copy=False); right = right.tocsr(copy=False)
    bound = _product_bound(left, right)
    integer_admission((left.shape[0], right.shape[1]), bound, index_dtype=index_dtype)
    entry_bytes = 16 + np.dtype(index_dtype).itemsize
    payload = bound * entry_bytes + (left.shape[0] + 1) * np.dtype(index_dtype).itemsize
    # This is a declared conservative assembly workspace allowance, not a
    # guarantee about SciPy/SuperLU's native allocator. The watchdog is final.
    _gate(allocation_gate, name, payload, payload, graph_bound_entries=bound,
          native_sparse_product_workspace_unknown=True)
    result = (left @ right).tocsr()
    result.sum_duplicates(); result.sort_indices()
    csr_audit(result, petsc_index_dtype=index_dtype)
    return result


def _adjoint(matrix, *, allocation_gate, name):
    payload = int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)
    _gate(allocation_gate, name, payload, payload,
          allocation_scope="before_sparse_conjugation_and_transpose_CSR_conversion")
    return matrix.conj().T.tocsr()


def _norm_squared(matrix):
    return float(np.vdot(matrix.data, matrix.data).real)


def positive_h_coordinate_scale(original_h):
    """Exact reversible auxiliary coordinate change, not a rebuilt carrier.

    R=diag(I,H_original^-1/2). This uses the carrier's original real-positive
    diagonal H, not Hhat after cell condensation. It neither deletes aliases
    nor recreates a functional lost to upstream absolute sparsification.
    """
    h = np.asarray(original_h)
    if (h.ndim != 1 or h.dtype.kind not in "fi" or not np.isfinite(h).all()
            or np.any(h <= 0)):
        raise ValueError("original carrier H must be finite real-positive")
    scale = 1 / np.sqrt(h.astype(np.float64))
    inverse = 1 / scale
    if not np.isfinite(scale).all() or not np.isfinite(inverse).all() or np.any(inverse == 0):
        raise ValueError("positive-H scale and inverse must remain finite/nonzero")
    if np.max(np.abs(scale * inverse - 1), initial=0) > LIMITS["mapping"]:
        raise ValueError("positive-H coordinate inverse gate fails")
    return scale, inverse


@dataclass
class AugmentedYCoordinates:
    trace: dict[str, Any]
    q_trace: sparse.csr_matrix
    aliases: tuple[np.ndarray, ...]
    eta_ports: np.ndarray
    original_port_keys: tuple[tuple[str, int, int, str], ...]
    port_count: int
    index_dtype: np.dtype
    audit: dict[str, Any]
    port_scale: np.ndarray | None = None

    @property
    def rows(self):
        return self.q_trace.shape[0] + self.port_count

    @property
    def ny(self):
        return int(self.trace["ny"])

    @property
    def width(self):
        return int(self.trace["trace_width"])

    @property
    def scale(self):
        return np.ones(self.port_count) if self.port_scale is None else self.port_scale

    def manufactured_native_dual(self, complete_modal_load):
        """b=P^-H f for P=R_aux Q_aug, with ALL modal slots embedded first."""
        f = np.asarray(complete_modal_load, dtype=np.complex128)
        nt = self.q_trace.shape[0]
        if f.shape != (self.rows,) or not np.isfinite(f).all():
            raise ValueError("manufactured load must include the complete modal inventory")
        result = np.empty_like(f)
        result[:nt] = self.trace["R_t_inverse"].conj().T @ (self.trace["F_t"] @ f[:nt])
        result[nt:] = f[nt:] / self.scale
        return result

    def q_map(self, q_index, *, allocation_gate):
        """Tall sparse primal map for one q and all its physical port aliases."""
        if not 0 <= q_index < self.ny:
            raise ValueError("q index is outside the complete inventory")
        ports = self.aliases[q_index]
        start, stop = q_index * self.width, (q_index + 1) * self.width
        _gate(allocation_gate, "q_trace_slice_selection_masks", workspace=3 * self.q_trace.nnz)
        slice_nnz = int(np.count_nonzero((self.q_trace.indices >= start) & (self.q_trace.indices < stop)))
        _gate(allocation_gate, "q_trace_column_slice", slice_nnz * (16 + self.index_dtype.itemsize)
              + (self.q_trace.shape[0] + 1) * self.index_dtype.itemsize,
              self.q_trace.nnz * 2, column_selection_mask_allowance=True)
        q = self.q_trace[:, q_index * self.width:(q_index + 1) * self.width]
        shape = (self.rows, self.width + len(ports))
        nnz = int(q.nnz) + len(ports)
        integer_admission(shape, nnz, index_dtype=self.index_dtype)
        _gate(allocation_gate, "one_q_primal_map", nnz * (16 + self.index_dtype.itemsize)
              + (self.rows + 1) * self.index_dtype.itemsize)
        port_map = sparse.csr_matrix((self.scale[ports].astype(complex),
                                      (ports, np.arange(len(ports)))),
                                     shape=(self.port_count, len(ports)))
        result = sparse.block_diag((q, port_map), format="csr")
        result.sum_duplicates(); result.sort_indices()
        return result

    def augmented_translation(self, *, allocation_gate):
        t = self.trace["native_trace_translation"]
        _gate(allocation_gate, "augmented_native_translation",
              (t.nnz + self.port_count) * (16 + self.index_dtype.itemsize)
              + (self.rows + 1) * self.index_dtype.itemsize)
        return sparse.block_diag((t, sparse.diags(self.eta_ports, format="csr")), format="csr")


def build_augmented_coordinates(trace, full_layout, carrier, modes, cfg, *, allocation_gate,
                                petsc_index_dtype, auxiliary_gauge="raw"):
    """Use existing full-space audit; never assume four ports in harmonic zero."""
    from src.solvers.task40extra_y_orbit_reference import audit_port_aliases

    expected_trace = {"R_t", "R_t_inverse", "F_t", "native_trace_translation", "trace_width",
                      "ny", "trace_original_rows", "full_independent_trace_positions",
                      "full_canonical_trace_positions", "audit"}
    if not expected_trace.issubset(trace):
        raise ValueError("exact trace restriction contract is incomplete")
    ports_audit = audit_port_aliases(carrier, full_layout, cfg, modes)
    if trace["ny"] != full_layout.ny or trace["R_t"].shape[0] != trace["ny"] * trace["trace_width"]:
        raise ValueError("trace restriction does not retain all y orbits")
    index_dtype = np.dtype(petsc_index_dtype)
    q_trace = _product(trace["R_t"], trace["F_t"], allocation_gate=allocation_gate,
                       name="trace_primal_Q_equals_R_F", index_dtype=index_dtype)
    aliases = tuple(np.asarray([entry["index"] for entry in ports_audit["alias_groups"][q]],
                               dtype=index_dtype) for q in range(full_layout.ny))
    if not np.array_equal(np.sort(np.concatenate(aliases)), np.arange(len(carrier.entries))):
        raise ValueError("all physical port indices must occur exactly once")
    keys = tuple((str(entry.mode_identity["side"]), int(entry.mode_identity["m"]),
                  int(entry.mode_identity["n"]), str(entry.mode_identity["polarization"]))
                 for entry in carrier.entries)
    eta = np.asarray([np.exp(1j * (complex(cfg.ky).real * cfg.period_y + 2 * np.pi * key[2])
                             / full_layout.ny) for key in keys])
    if auxiliary_gauge not in ("raw", "positive-h"):
        raise ValueError("unreviewed auxiliary coordinate gauge")
    original_h = np.asarray([entry.normalization_h for entry in carrier.entries])
    positive_scale, inverse_scale = positive_h_coordinate_scale(original_h)
    port_scale = positive_scale if auxiliary_gauge == "positive-h" else np.ones(len(keys))
    return AugmentedYCoordinates(trace, q_trace, aliases, eta, keys, len(keys), index_dtype,
        {"all_q": list(range(full_layout.ny)), "trace": trace["audit"], "ports": ports_audit,
         "augmented_primal_map": "P=R_aux Q_aug; R_aux=diag(I,H_original^-1/2) if positive-h",
         "augmented_dual_map": "P^H, not P^-1",
         "alias_counts": [len(v) for v in aliases], "port_normalization_changed": False,
         "all_internal_y_channels_retained": True,
         "auxiliary_gauge": auxiliary_gauge, "original_H_min": float(np.min(original_h)),
         "original_H_max": float(np.max(original_h)),
         "scale_min": float(np.min(port_scale)), "scale_max": float(np.max(port_scale)),
         "positive_H_scale_inverse_finite": True, "Hhat_assumed_diagonal": False,
         "same_frozen_eliminated_FE_operator": True,
         "upstream_clipped_functionals_restored": False,
         "original_zero_coupling_functionals": sum(len(e.coupling_rows) == 0 for e in carrier.entries),
         "original_zero_projection_functionals": sum(len(e.projection_rows) == 0 for e in carrier.entries)},
        port_scale)


class SparseAllQFactor:
    """Existing condensed inverse's solve_repeated API with all q factors.

    Pass one audits all cross-q blocks and native variational covariance.
    Only after every symmetry gate passes does pass two create real factors.
    Off-block roundoff is dropped at that point, with its full measured norm.
    """
    def __init__(self, matrix, coordinates, *, allocation_gate, event, save_array,
                 factor_allowance_bytes=FACTOR_ALLOWANCE_BYTES, save_factor_diagnostic=None):
        self.coordinates = coordinates
        self.gate = allocation_gate
        self.factors = []
        self.calls = 0
        self.destroyed = False
        self.audit = {"schema": SCHEMA, "factor_backend": "SciPy public SuperLU splu",
                      "factor_memory_unknown": True, "factor_L_U_stat_copies_created": False,
                      "factor_reuse_plus_minus_q": False, "all_q_factors": coordinates.ny,
                      "declared_additional_factor_allowance_bytes": int(factor_allowance_bytes),
                      "factor_allowance_is_memory_guarantee": False,
                      "global_dense_FE_or_modal_matrix_created": False,
                      "independent_load_coordinates": coordinates.audit.get("auxiliary_gauge", "raw"),
                      "factor_passes": "all-cross-q-audit then streamed per-q factors"}
        try:
            self._setup(matrix, coordinates, allocation_gate=allocation_gate, event=event,
                        save_array=save_array, factor_allowance_bytes=factor_allowance_bytes,
                        save_factor_diagnostic=save_factor_diagnostic)
        except BaseException:
            self.destroy()
            raise

    def _setup(self, matrix, coordinates, *, allocation_gate, event, save_array,
               factor_allowance_bytes, save_factor_diagnostic):
        started = perf_counter()
        csr_facts = csr_audit(matrix, petsc_index_dtype=coordinates.index_dtype)
        if matrix.shape != (coordinates.rows, coordinates.rows):
            raise ValueError("condensed augmented inventory differs from the actual matrix")
        self.audit["condensed_CSR"] = csr_facts
        self.audit["condensed_CSR_sha256"] = sparse_hash(matrix)
        _gate(allocation_gate, "initial_factor_policy_admission", workspace=factor_allowance_bytes,
              evidence_reserve_bytes=EVIDENCE_RESERVE_BYTES,
              resident_factor_count=0, guarantee=False)
        native = coordinates.augmented_translation(allocation_gate=allocation_gate)
        mt = _product(matrix, native, allocation_gate=allocation_gate,
                      name="native_augmented_S_T", index_dtype=coordinates.index_dtype)
        native_dual = _adjoint(native, allocation_gate=allocation_gate, name="native_translation_adjoint")
        shifted = _product(native_dual, mt, allocation_gate=allocation_gate,
                           name="native_augmented_T_H_S_T", index_dtype=coordinates.index_dtype)
        del native, native_dual, mt
        _gate(allocation_gate, "native_covariance_difference",
              payload=csr_facts["payload_bytes"] + shifted.data.nbytes
              + shifted.indices.nbytes + shifted.indptr.nbytes)
        difference = shifted - matrix
        covariance = float(np.sqrt(_norm_squared(difference) /
                          max(_norm_squared(matrix), np.finfo(float).tiny)))
        del difference, shifted
        self.audit["native_condensed_augmented_form_covariance_relative"] = covariance
        if not np.isfinite(covariance) or covariance > LIMITS["operator"]:
            raise ValueError(f"native variational covariance gate fails: {covariance}")
        diagonal_sq = off_sq = off_max = 0.0
        block_facts = []
        pair_facts = []
        for q in range(coordinates.ny):
            right = coordinates.q_map(q, allocation_gate=allocation_gate)
            product = _product(matrix, right, allocation_gate=allocation_gate,
                               name=f"audit_S_Q_{q}", index_dtype=coordinates.index_dtype)
            for p in range(coordinates.ny):
                left = right if p == q else coordinates.q_map(p, allocation_gate=allocation_gate)
                left_dual = _adjoint(left, allocation_gate=allocation_gate, name=f"audit_Q_{p}_adjoint")
                block = _product(left_dual, product, allocation_gate=allocation_gate,
                                 name=f"audit_Q_{p}_H_S_Q_{q}", index_dtype=coordinates.index_dtype)
                norm_sq = _norm_squared(block)
                pair_facts.append({"p": p, "q": q, "frobenius_norm": float(np.sqrt(norm_sq)),
                                   "absolute_max": float(np.max(np.abs(block.data))) if block.nnz else 0.0})
                if p == q:
                    diagonal_sq += norm_sq
                    facts = {"q": q, "shape": list(block.shape), "nnz": int(block.nnz),
                             "CSR_sha256": sparse_hash(block),
                             "CSR": csr_audit(block, petsc_index_dtype=coordinates.index_dtype)}
                    block_facts.append(facts)
                else:
                    off_sq += norm_sq
                    if block.nnz:
                        off_max = max(off_max, float(np.max(np.abs(block.data))))
                del block, left_dual
                if p != q:
                    del left
            del product, right
            event("cross_q_column_audited", {"q": q, "all_left_q_checked": coordinates.ny,
                                             "factor_count": 0})
        off_relative = float(np.sqrt(off_sq / max(off_sq + diagonal_sq, np.finfo(float).tiny)))
        diagonal_norms = {item["q"]: item["frobenius_norm"] for item in pair_facts if item["p"] == item["q"]}
        if any(value == 0 for value in diagonal_norms.values()):
            # Every q remains a real inverse block. An all-zero diagonal block
            # cannot be silently omitted, even if its cross-blocks are zero.
            event("zero_diagonal_q_controlled_stop", {"diagonal_norms": diagonal_norms,
                  "block_pairs": pair_facts, "factor_count": 0})
            raise ValueError("all-q inverse requires nonzero diagonal blocks; no zero-sector omission")
        for item in pair_facts:
            p, q = item["p"], item["q"]
            item.update(row_diagonal_frobenius_norm=diagonal_norms[p],
                        column_diagonal_frobenius_norm=diagonal_norms[q],
                        relative_to_row_diagonal=item["frobenius_norm"] / diagonal_norms[p],
                        relative_to_column_diagonal=item["frobenius_norm"] / diagonal_norms[q],
                        per_pair_limit=LIMITS["operator"] if p != q else None)
            item["passed"] = (p == q or max(item["relative_to_row_diagonal"],
                                             item["relative_to_column_diagonal"]) <= LIMITS["operator"])
        self.audit.update(modal_off_block_relative=off_relative,
                          modal_off_block_absolute_max=off_max, input_blocks=block_facts,
                          all_block_pair_diagnostics=pair_facts,
                          per_pair_scale="max(||S_pq||F/||S_pp||F, ||S_pq||F/||S_qq||F)",
                          zero_diagonal_policy="controlled stop, all q must be invertible",
                          group_averaged_reference_used=False,
                          discarded_entries="only complete audited roundoff cross-q blocks")
        if (not np.isfinite(off_relative) or off_relative > LIMITS["operator"]
                or any(not item["passed"] for item in pair_facts)):
            raise ValueError(f"all-q off-block gate fails: {off_relative}")
        event("all_symmetry_gates_pass_before_factor", self.audit)
        for q in range(coordinates.ny):
            right = coordinates.q_map(q, allocation_gate=allocation_gate)
            product = _product(matrix, right, allocation_gate=allocation_gate,
                               name=f"factor_S_Q_{q}", index_dtype=coordinates.index_dtype)
            right_dual = _adjoint(right, allocation_gate=allocation_gate, name=f"factor_Q_{q}_adjoint")
            block = _product(right_dual, product, allocation_gate=allocation_gate,
                             name=f"factor_Q_{q}_H_S_Q_{q}", index_dtype=coordinates.index_dtype)
            del right, right_dual, product
            if sparse_hash(block) != block_facts[q]["CSR_sha256"]:
                raise RuntimeError("recomputed diagonal block differs from the audited block")
            for suffix, values in (("data", block.data), ("indices", block.indices), ("indptr", block.indptr)):
                save_array(f"q_{q}_S_{suffix}", values)
            # Already resident factors are in measured RSS. Reserve only the
            # remaining share, rather than adding the original 512 MiB again.
            remaining = factor_allowance_bytes * (coordinates.ny - q) // coordinates.ny
            payload = block_facts[q]["CSR"]["payload_bytes"]
            _gate(allocation_gate, f"q_{q}_CSC_conversion_and_factor", payload, remaining,
                  evidence_reserve_bytes=EVIDENCE_RESERVE_BYTES,
                  resident_factor_count=len(self.factors), remaining_q_factors=coordinates.ny - q,
                  LU_fill_and_workspace_unknown=True)
            csc = block.tocsc()
            integer_admission(csc.shape, csc.nnz, index_dtype=csc.indices.dtype,
                              indptr_dtype=csc.indptr.dtype)
            # SciPy's bundled SuperLU wrapper uses signed C-int indices even
            # if a future caller selects an int64 PETSc ABI. Never infer that
            # a wider PETSc build makes this small-pilot backend target-ready.
            integer_admission(csc.shape, csc.nnz, index_dtype=np.int32)
            del block
            factor = splu(csc)
            values = np.arange(csc.shape[0])
            a = np.cos(.17 * values) + 1j * np.sin(.31 * values)
            b = np.sin(.23 * values) + 1j * np.cos(.41 * values)
            xa = factor.solve(a); xa_repeat = factor.solve(a)
            xb = factor.solve(b); xsum = factor.solve(a + b)
            diagnostic_vectors = {"rhs_a": a, "rhs_b": b, "solution_a": xa,
                                  "solution_b": xb, "solution_a_repeat": xa_repeat,
                                  "solution_sum": xsum}
            finite = {name: bool(np.isfinite(values).all()) for name, values in diagnostic_vectors.items()}
            # Honest bounded raw diagnostics are distinct from finite-only
            # successful evidence. Preserve values/counts BEFORE assertions.
            if callable(save_factor_diagnostic):
                for name, values in diagnostic_vectors.items():
                    save_factor_diagnostic(f"q_{q}_{name}", values)
            event("factor_raw_finiteness_before_gate", {"q": q, "finite": finite,
                  "coordinate_gauge": coordinates.audit.get("auxiliary_gauge", "raw")})
            if not all(finite.values()):
                raise FloatingPointError("q factor produced nonfinite vectors; raw diagnostics preserved")
            repeated = _relative(xa_repeat - xa, xa)
            linearity = _relative(xsum - xa - xb, xsum)
            true_residual = max(_relative(csc @ xa - a, a), _relative(csc @ xb - b, b))
            block_facts[q].update(repeated_solve_relative=repeated,
                                  linearity_relative=linearity,
                                  block_true_residual_relative_max=true_residual)
            if (not np.isfinite([repeated, linearity, true_residual]).all()
                    or repeated > LIMITS["operator"] or linearity > LIMITS["operator"]
                    or true_residual > LIMITS["residual"]):
                raise ValueError(f"actual q-block factor repeated/linear/residual gate fails: {block_facts[q]}")
            # Embed a one-q manufactured load in the COMPLETE modal inventory
            # before b=P^-H f. This is not a change to the fixed original FE
            # generic/physical RHS, and not Q^-H without the auxiliary R.
            native_residuals = []
            for label, load, solution in (("a", a, xa), ("b", b, xb)):
                complete = np.zeros(coordinates.rows, dtype=np.complex128)
                nt = coordinates.q_trace.shape[0]
                rows = slice(q * coordinates.width, (q + 1) * coordinates.width)
                complete[rows] = load[:coordinates.width]
                complete[nt + coordinates.aliases[q]] = load[coordinates.width:]
                native_rhs = coordinates.manufactured_native_dual(complete)
                primal = coordinates.q_map(q, allocation_gate=allocation_gate)
                native_solution = np.asarray(primal @ solution)
                original_action = np.asarray(matrix @ native_solution)
                for name, values in (("complete_modal_load", complete), ("native_rhs", native_rhs),
                                     ("native_solution", native_solution), ("original_S_action", original_action)):
                    save_array(f"q_{q}_manufactured_{label}_{name}", values)
                residual = _relative(original_action - native_rhs, native_rhs)
                native_residuals.append(residual)
                del complete, native_rhs, primal, native_solution, original_action
            block_facts[q]["manufactured_original_S_residuals"] = native_residuals
            if max(native_residuals) > LIMITS["residual"]:
                raise ValueError("manufactured equilibrated load failed ORIGINAL S0 residual")
            del a, b, xa, xa_repeat, xb, xsum
            # No access to factor.L/U: those properties materialize copies.
            del csc
            self.factors.append(factor)
            event("q_factor_retained", {"q": q, "all_q_required": coordinates.ny,
                                         "retained_factor_count": len(self.factors),
                                         "factor_memory_bytes": None})
        self.audit["setup_seconds"] = perf_counter() - started

    def solve_array(self, rhs):
        if self.destroyed or len(self.factors) != self.coordinates.ny:
            raise RuntimeError("complete live all-q factor inventory is required")
        rhs = np.asarray(rhs, dtype=np.complex128)
        if rhs.shape != (self.coordinates.rows,) or not np.isfinite(rhs).all():
            raise ValueError("invalid complete augmented dual RHS")
        nt = self.coordinates.q_trace.shape[0]
        qt = self.coordinates.q_trace
        _gate(self.gate, "complete_augmented_dual_RHS_and_reconstruction",
              qt.data.nbytes + qt.indices.nbytes + qt.indptr.nbytes,
              workspace=8 * self.coordinates.rows * 16)
        trace_rhs = np.asarray(self.coordinates.q_trace.conj().T @ rhs[:nt])
        trace_solution = np.empty_like(trace_rhs)
        result = np.zeros_like(rhs)
        for q, factor in enumerate(self.factors):
            rows = slice(q * self.coordinates.width, (q + 1) * self.coordinates.width)
            ports = self.coordinates.aliases[q]
            dual_rhs = np.concatenate((trace_rhs[rows], self.coordinates.scale[ports] * rhs[nt + ports]))
            primal = factor.solve(dual_rhs)
            trace_solution[rows] = primal[:self.coordinates.width]
            result[nt + ports] = self.coordinates.scale[ports] * primal[self.coordinates.width:]
        result[:nt] = self.coordinates.q_trace @ trace_solution
        if not np.isfinite(result).all():
            raise FloatingPointError("all-q factor returned nonfinite original augmented solution")
        self.calls += 1
        return result

    def solve_repeated(self, rhs, target):
        target.array[:] = self.solve_array(rhs.getArray(readonly=True))

    def destroy(self):
        self.factors.clear()
        self.destroyed = True


class FullRecoveredReferenceInverse:
    """Right-PC wrapper: original full interior RHS in, full primal recovery out."""
    def __init__(self, reference, full_layout, factor):
        self.reference, self.full_layout = reference, full_layout
        reference.inverse.factor = factor
        self.calls = 0

    def apply_array(self, rhs):
        solution = self.reference.apply_independent(rhs, self.full_layout)
        self.calls += 1
        return solution

    def apply(self, _pc, source, target):
        target.array[:] = self.apply_array(source.getArray(readonly=True))


def audit_full_form_covariance(action, full_layout, probes):
    """Full original FE/DtN action including all interiors, never trace-only."""
    t = full_layout.native_translation
    defects = []
    for source in probes:
        base = action.apply(source)
        shifted = t.conj().T @ action.apply(t @ source)
        defects.append(_relative(shifted - base, base))
    worst = max(defects)
    if not np.isfinite(worst) or worst > LIMITS["operator"]:
        raise ValueError(f"full original native form covariance gate fails: {worst}")
    return {"full_original_covariance_action_relative_max": worst,
            "probe_values": defects, "probe_count": len(defects),
            "authority": "full original FE/DtN action, sampled vectors, not a full-matrix norm"}


def audit_condensation_covariance(reference, full_layout, coordinates, probes, *, allocation_gate):
    """Full-to-condensed dual reduction intertwines translations with recovery."""
    # A dual RHS transforms as T^H, not T^-1. Static condensation must obey
    # reduce(T_full^H b) = T_aug^H reduce(b), including nonzero interior RHS.
    t = full_layout.native_translation
    ta = coordinates.augmented_translation(allocation_gate=allocation_gate)
    defects = []
    for rhs in probes:
        reduced = reference.reduce_independent(rhs, full_layout)
        translated = reference.reduce_independent(t.conj().T @ rhs, full_layout)
        defects.append(_relative(translated - ta.conj().T @ reduced, reduced))
    del ta
    worst = max(defects)
    if not np.isfinite(worst) or worst > LIMITS["operator"]:
        raise ValueError(f"complete interior-RHS condensation covariance gate fails: {worst}")
    return {"complete_RHS_reduction_covariance_relative_max": worst,
            "probe_values": defects, "all_original_interiors_in_probes": True,
            "not_a_trace_only_symmetry_test": True}


def sampled_right_pc_defect(action0, action1, inverse, rhs):
    """Expose weak perturbations; this sample is not an operator-norm bound."""
    applied = inverse.apply_array(rhs)
    return _relative(action1.apply(applied) - action0.apply(applied), rhs)
