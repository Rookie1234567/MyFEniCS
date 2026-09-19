"""Physical p4 interface Schur core for the Task39extra V14 route.

The production path in this module owns the p4 internal elimination and the
sparse interface matrix, while the mesh, MPC, physical form and port carrier
remain owned by the caller.  It does not construct the historical macro
``Q/D/W`` objects or any p2/p1 level.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import hashlib
import math
import time
from typing import Any, Callable

import numpy as np


SCHUR_SCHEMA = "task039extra.physical-interface-schur.v14"
SCHUR_PROFILE = "physical_p4_schur_v14"
MAX_INTERNAL_ROWS = 2048
MAX_INTERFACE_ROWS = 512
MAX_INTERFACE_WORKSPACE_BYTES = 64 * 1024**2
SCHUR_BATCH_COLUMNS = 32
V11_MIN_BYTES = 32 * 1024**2
V11_PADDING_BYTES = 8 * 1024**2


def _sparse_payload_bytes(nnz: int, rows: int, petsc: Any) -> int:
    return int(rows + 1) * np.dtype(petsc.IntType).itemsize + int(nnz) * (
        np.dtype(petsc.IntType).itemsize + np.dtype(petsc.ScalarType).itemsize
    )


def v11_memory_request_mb(
    symbolic_raw: Mapping[str, Any], *, blr: bool = False
) -> dict[str, Any]:
    """Return the exact decimal-MB request prescribed by Review V14.

    MUMPS ``INFOG(16)`` is an integer estimate in megabytes.  The estimate is
    interpreted as a sizing input, not as a measured peak.  The explicit BLR
    route additionally admits the native ``INFOG(36/37)`` fields and sizes
    from ``max(16, 17, 36, 37)`` without rewriting any raw backend value.
    """

    from .fullspace_bounded_mumps import symbolic_sized_local_mumps_request

    infog = symbolic_raw.get("infog")
    if not blr:
        result = dict(symbolic_sized_local_mumps_request(symbolic_raw, mpi_size=1))
    else:
        if not isinstance(infog, Mapping):
            raise RuntimeError("MEMORY_POLICY_UNSUPPORTED: MUMPS INFOG is unavailable")
        values: dict[str, int] = {}
        for key in ("16", "17", "36", "37"):
            value = infog.get(key)
            if type(value) is not int or value < 0:
                raise RuntimeError(
                    "MEMORY_POLICY_UNSUPPORTED: BLR INFOG "
                    f"{key} is not a non-negative integer"
                )
            values[key] = int(value)
        estimate_mb = max(values.values())
        estimate_bytes = 1_000_000 * (1 + estimate_mb)
        minimum_request = max(
            32 * 1024**2,
            2 * estimate_bytes + 8 * 1024**2,
        )
        request_bytes = 1_000_000 * math.ceil(minimum_request / 1_000_000)
        result = {
            "policy": "SYMBOLIC_SIZED_LOCAL_MUMPS_V11",
            "mpi_size": 1,
            "infog16_mb": values["16"],
            "infog17_mb": values["17"],
            "infog36_symbolic_max_mb": values["36"],
            "infog37_symbolic_sum_mb": values["37"],
            "sizing_estimate_mb": int(estimate_mb),
            "estimate_bytes": int(estimate_bytes),
            "minimum_request_bytes": int(minimum_request),
            "request_bytes": int(request_bytes),
            "request_mb": int(request_bytes // 1_000_000),
            "unit_bytes": 1_000_000,
            "rounding": "decimal_MB_ceiling",
            "sizing_formula": "max(INFOG(16),INFOG(17),INFOG(36),INFOG(37))",
            "raw_fields_preserved": True,
        }
    result.update(
        {
            "formula": (
                "ceil_MB(max(32 MiB, 2*symbolic_estimate_padded+8 MiB))"
            ),
            "symbolic_estimate_mb": int(
                result.get("sizing_estimate_mb", result["infog16_mb"])
            ),
            "symbolic_estimate_padded_bytes": int(result["estimate_bytes"]),
            "requested_memory_limit_mb": int(result["request_mb"]),
            "unit": "decimal_MB_for_MUMPS_ICNTL_23",
            "blr_sizing": bool(blr),
        }
    )
    return result


def _as_complex_array(value: Any) -> np.ndarray:
    if hasattr(value, "array"):
        return np.asarray(value.array)
    getter = getattr(value, "getArray", None)
    if callable(getter):
        try:
            return np.asarray(getter(readonly=True))
        except TypeError:
            return np.asarray(getter())
    return np.asarray(value)


def _destroy(value: Any) -> None:
    destroy = getattr(value, "destroy", None)
    if callable(destroy):
        destroy()


def _nonzero_rows(values: Any, *, tolerance: float = 0.0) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1:
        array = array.reshape(-1)
    return np.flatnonzero(np.abs(array) > tolerance).astype(np.int64)


def _complex_matrix(
    value: Any,
    *,
    name: str,
    max_rows: int | None = None,
) -> np.ndarray:
    """Convert one small Q3 matrix to a finite square complex array."""

    raw_shape = getattr(value, "shape", None)
    if max_rows is not None and raw_shape is not None:
        try:
            if len(raw_shape) >= 1 and int(raw_shape[0]) > int(max_rows):
                raise ValueError(f"{name} exceeds the {int(max_rows)}-row limit")
        except TypeError:
            # An object without a usable shape is checked after conversion.
            pass
    if hasattr(value, "toarray"):
        value = value.toarray()
    array = np.asarray(value, dtype=np.complex128)
    if array.ndim != 2 or array.shape[0] != array.shape[1]:
        raise ValueError(f"{name} must be a square two-dimensional matrix")
    if max_rows is not None and array.shape[0] > int(max_rows):
        raise ValueError(f"{name} exceeds the {int(max_rows)}-row limit")
    if array.shape[0] == 0 or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be nonempty and finite")
    return np.ascontiguousarray(array)


def _direction_matrix(value: Any, *, name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.complex128)
    if array.ndim != 2 or array.shape[1] == 0:
        raise ValueError(f"{name} must be a nonempty two-dimensional direction matrix")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains non-finite entries")
    # Preserve an already-qualified caller-owned layout.  In particular, the
    # two-pass MGS output is a transposed view of its row-major storage and is
    # intentionally borrowed by the coarse pair.  A C-contiguous conversion
    # here would silently create a second resident P/Q library.
    return array


def _array_sha256(value: Any) -> str:
    array = np.ascontiguousarray(np.asarray(value))
    return hashlib.sha256(array.view(np.uint8)).hexdigest()


def _operator_apply(operator: Any, vectors: np.ndarray, *, name: str) -> np.ndarray:
    """Apply one explicit block action without hiding retries or column loops.

    A callback supplied here must accept the complete two-dimensional block and
    return a block with exactly the same shape.  Callers that only have a
    vector action must wrap it explicitly at the production boundary; this
    helper never retries a failed block call one column at a time.
    """

    vectors = np.asarray(vectors, dtype=np.complex128)
    if vectors.ndim != 2:
        raise ValueError(f"{name} requires a two-dimensional block")
    if callable(operator):
        result = operator(vectors.copy())
    elif hasattr(operator, "dot"):
        result = operator.dot(vectors)
    else:
        result = operator @ vectors
    result = _as_complex_array(result)
    if result.shape != vectors.shape:
        raise ValueError(
            f"{name} block action returned shape {result.shape}; "
            f"expected {vectors.shape}"
        )
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} returned non-finite values")
    return np.ascontiguousarray(result)


@dataclass(frozen=True)
class PairedPatchBasis:
    """A bounded two-sided local SVD basis for one physical interface patch.

    ``P`` contains right directions and ``Q`` contains left directions.  They
    are stored after the positive diagonal scaling, so each side is
    orthonormal in the corresponding Delta-weighted inner product.  This
    object is pure small-matrix evidence; it does not retain a reference field
    or a global Schur matrix.
    """

    patch_id: int | str
    P: np.ndarray
    Q: np.ndarray
    singular_values: np.ndarray
    checks: dict[str, Any]
    svd_driver: str = "gesvd"

    @property
    def rows(self) -> int:
        return int(self.P.shape[0])

    @property
    def rank(self) -> int:
        return int(self.P.shape[1])

    def audit(self) -> dict[str, Any]:
        return {
            "schema": "task039extra.v14.paired-patch-basis.v1",
            "patch_id": self.patch_id,
            "rows": self.rows,
            "rank": self.rank,
            "svd_driver": self.svd_driver,
            "singular_values": self.singular_values.tolist(),
            "checks": dict(self.checks),
        }


def build_paired_patch_basis(
    local_schur: Any,
    delta: Any,
    *,
    patch_id: int | str,
    max_pairs: int = 8,
    pair_rtol: float = 1.0e-12,
    action_atol: float = 1.0e-10,
    max_workspace_bytes: int = 1 << 30,
) -> PairedPatchBasis:
    """Build the fixed, paired ``gesvd`` directions for one local Schur patch.

    The local matrix is intentionally limited to the Review V14 patch size.
    The smallest singular values are selected deterministically, while the
    left and right vectors remain paired even for a non-Hermitian matrix.  The
    returned ``P``/``Q`` are the Delta-scaled vectors used by the interface
    coarse pair; callers must add any patch restriction/weight maps explicitly.
    """

    if not isinstance(max_pairs, (int, np.integer)) or not 1 <= int(max_pairs) <= 8:
        raise ValueError("max_pairs must be between 1 and 8")
    if not np.isfinite(pair_rtol) or pair_rtol <= 0:
        raise ValueError("pair_rtol must be positive and finite")
    if not np.isfinite(action_atol) or action_atol <= 0:
        raise ValueError("action_atol must be positive and finite")
    if (
        not isinstance(max_workspace_bytes, (int, np.integer))
        or int(max_workspace_bytes) <= 0
    ):
        raise ValueError("max_workspace_bytes must be positive")
    matrix = _complex_matrix(
        local_schur,
        name="local_schur",
        max_rows=MAX_INTERNAL_ROWS,
    )
    rows = int(matrix.shape[0])
    delta_array = np.asarray(delta)
    if delta_array.ndim == 2:
        if delta_array.shape != (rows, rows):
            raise ValueError("Delta matrix has the wrong shape")
        delta_array = np.diag(delta_array)
    delta_array = np.asarray(delta_array, dtype=np.complex128).reshape(-1)
    if delta_array.size != rows or not np.all(np.isfinite(delta_array)):
        raise ValueError("Delta must be a finite positive diagonal of local Schur size")
    if np.max(np.abs(delta_array.imag), initial=0.0) > 1.0e-14:
        raise ValueError("Delta must be real and positive")
    delta_real = np.asarray(delta_array.real, dtype=np.float64)
    if np.any(delta_real <= 0):
        raise ValueError("Delta must be strictly positive")

    from scipy.linalg import svd

    scalar_bytes = np.dtype(np.complex128).itemsize
    # This is a deliberately fixed conservative preflight for the single
    # patch SVD.  It includes the scaled input, a possible LAPACK input copy,
    # both full singular-vector arrays, reconstruction/selection temporaries,
    # and a bounded vector allowance.  The caller accounts the retained Si/LU
    # separately in its resident inventory.
    matrix_bytes = int(rows * rows * scalar_bytes)
    svd_workspace_bound_bytes = int(
        12 * matrix_bytes + 8 * rows * scalar_bytes
    )
    if svd_workspace_bound_bytes > int(max_workspace_bytes):
        raise MemoryError(
            "PAIRED_PATCH_SVD_WORKSPACE_EXCEEDED: "
            f"{svd_workspace_bound_bytes} > {int(max_workspace_bytes)} bytes"
        )
    delta_inv_sqrt = 1.0 / np.sqrt(delta_real)
    scaled = delta_inv_sqrt[:, None] * matrix * delta_inv_sqrt[None, :]
    left, singular_values, right_h = svd(
        scaled,
        full_matrices=False,
        check_finite=True,
        lapack_driver="gesvd",
        overwrite_a=False,
    )
    left = np.asarray(left, dtype=np.complex128)
    singular_values = np.asarray(singular_values, dtype=np.float64)
    right_h = np.asarray(right_h, dtype=np.complex128)
    if (
        left.shape != scaled.shape
        or right_h.shape != scaled.shape
        or singular_values.shape != (rows,)
        or not np.all(np.isfinite(left))
        or not np.all(np.isfinite(singular_values))
        or not np.all(np.isfinite(right_h))
    ):
        raise FloatingPointError("local paired SVD returned invalid factors")

    tiny = np.finfo(np.float64).tiny
    operator_norm = float(abs(singular_values[0]))
    full_left_scaled = left * singular_values[None, :]
    reconstructed = full_left_scaled @ right_h
    reconstruction_error = reconstructed - scaled
    reconstruction_workspace_bytes = int(
        full_left_scaled.nbytes + reconstructed.nbytes + reconstruction_error.nbytes
    )
    full_reconstruction_relative = float(
        np.linalg.norm(reconstruction_error, ord="fro")
        / max(tiny, float(np.linalg.norm(scaled, ord="fro")))
    )
    del full_left_scaled, reconstructed, reconstruction_error
    order = np.argsort(singular_values, kind="stable")[: int(max_pairs)]
    selected_sigma = np.asarray(singular_values[order], dtype=np.float64)
    selected_left = np.asarray(left[:, order], dtype=np.complex128)
    # Select rows before conjugating/transposing.  ``right_h.conj().T[:,
    # order]`` would first materialize another full n-by-n array.
    selected_right = np.asarray(right_h[order, :].conj().T, dtype=np.complex128)
    P = delta_inv_sqrt[:, None] * selected_right
    Q = delta_inv_sqrt[:, None] * selected_left
    if not np.all(np.isfinite(P)) or not np.all(np.isfinite(Q)):
        raise FloatingPointError("paired local SVD directions are non-finite")

    identity = np.eye(selected_sigma.size, dtype=np.complex128)
    p_gram = P.conj().T @ (delta_real[:, None] * P)
    q_gram = Q.conj().T @ (delta_real[:, None] * Q)
    right_error = scaled @ selected_right - selected_left * selected_sigma[None, :]
    scaled_adjoint = np.empty_like(scaled)
    np.conjugate(scaled.T, out=scaled_adjoint)
    left_error = scaled_adjoint @ selected_left - selected_right * selected_sigma[None, :]
    left_norms = np.linalg.norm(selected_left, axis=0)
    right_norms = np.linalg.norm(selected_right, axis=0)
    sigma_norms = np.abs(selected_sigma)
    right_operation_scales = np.maximum(
        tiny,
        operator_norm * right_norms + sigma_norms * left_norms,
    )
    left_operation_scales = np.maximum(
        tiny,
        operator_norm * left_norms + sigma_norms * right_norms,
    )
    right_action_relative_per_pair = (
        np.linalg.norm(right_error, axis=0) / right_operation_scales
    )
    left_action_relative_per_pair = (
        np.linalg.norm(left_error, axis=0) / left_operation_scales
    )
    right_operation_scale = max(
        tiny,
        operator_norm * float(np.linalg.norm(selected_right, ord="fro"))
        + float(np.linalg.norm(selected_left * selected_sigma[None, :], ord="fro")),
    )
    left_operation_scale = max(
        tiny,
        operator_norm * float(np.linalg.norm(selected_left, ord="fro"))
        + float(np.linalg.norm(selected_right * selected_sigma[None, :], ord="fro")),
    )
    right_action_relative = float(
        np.linalg.norm(right_error, ord="fro") / right_operation_scale
    )
    left_action_relative = float(
        np.linalg.norm(left_error, ord="fro") / left_operation_scale
    )
    scaled_adjoint_bytes = int(scaled_adjoint.nbytes)
    lapack_input_copy_bytes = matrix_bytes
    svd_workspace_bytes = int(
        max(
            svd_workspace_bound_bytes,
            lapack_input_copy_bytes
            + sum(
                int(array.nbytes)
                for array in (
                    scaled,
                    left,
                    singular_values,
                    right_h,
                    selected_left,
                    selected_right,
                    P,
                    Q,
                    scaled_adjoint,
                    right_error,
                    left_error,
                    p_gram,
                    q_gram,
                    identity,
                )
            ),
        )
    )
    gram_scale = max(tiny, float(np.linalg.norm(identity, ord="fro")))
    p_gram_relative = float(np.linalg.norm(p_gram - identity, ord="fro") / gram_scale)
    q_gram_relative = float(np.linalg.norm(q_gram - identity, ord="fro") / gram_scale)
    checks = {
        "finite": True,
        "rows": rows,
        "rank": int(selected_sigma.size),
        "svd_driver": "gesvd",
        "pair_relative_tolerance": float(pair_rtol),
        "action_tolerance": float(action_atol),
        "right_action_relative": right_action_relative,
        "left_action_relative": left_action_relative,
        "right_action_relative_per_pair": right_action_relative_per_pair.tolist(),
        "left_action_relative_per_pair": left_action_relative_per_pair.tolist(),
        "right_operation_scales": right_operation_scales.tolist(),
        "left_operation_scales": left_operation_scales.tolist(),
        "pair_operation_scale_definition": (
            "||T||*||v||+|sigma|*||u|| for right; "
            "||T||*||u||+|sigma|*||v|| for left"
        ),
        "right_delta_orthogonality": float(np.linalg.norm(p_gram - identity)),
        "left_delta_orthogonality": float(np.linalg.norm(q_gram - identity)),
        "right_delta_subspace_gram_relative": p_gram_relative,
        "left_delta_subspace_gram_relative": q_gram_relative,
        "full_reconstruction_relative": full_reconstruction_relative,
        "reconstruction_workspace_bytes": reconstruction_workspace_bytes,
        "svd_workspace_bytes": svd_workspace_bytes,
        "svd_workspace_bound_bytes": svd_workspace_bound_bytes,
        "lapack_input_copy_bytes": lapack_input_copy_bytes,
        "scaled_adjoint_bytes": scaled_adjoint_bytes,
        "operator_scale": operator_norm,
        "operator_frobenius_norm": float(np.linalg.norm(scaled, ord="fro")),
        "p_sha256": _array_sha256(P),
        "q_sha256": _array_sha256(Q),
        "accepted_as_paired": True,
    }
    if (
        max(
            checks["right_action_relative"],
            checks["left_action_relative"],
            max(right_action_relative_per_pair, default=0.0),
            max(left_action_relative_per_pair, default=0.0),
        )
        > action_atol
        or full_reconstruction_relative > action_atol
    ):
        raise FloatingPointError(f"local paired SVD action check failed: {checks}")
    del scaled_adjoint, left, right_h, scaled
    return PairedPatchBasis(
        patch_id=patch_id,
        P=np.ascontiguousarray(P),
        Q=np.ascontiguousarray(Q),
        singular_values=np.ascontiguousarray(selected_sigma),
        checks=checks,
    )


@dataclass(frozen=True)
class PairedInterfaceBasis:
    """The globally ordered, independently normalized P/Q candidate pair."""

    P: np.ndarray
    Q: np.ndarray
    accepted_indices: np.ndarray
    rejected_indices: np.ndarray
    unprocessed_indices: np.ndarray
    checks: dict[str, Any]

    @property
    def ambient_rows(self) -> int:
        return int(self.P.shape[0])

    @property
    def rank(self) -> int:
        return int(self.P.shape[1])

    def audit(self) -> dict[str, Any]:
        return {
            "schema": "task039extra.v14.paired-interface-basis.v1",
            "ambient_rows": self.ambient_rows,
            "rank": self.rank,
            "accepted_indices": self.accepted_indices.tolist(),
            "rejected_indices": self.rejected_indices.tolist(),
            "unprocessed_indices": self.unprocessed_indices.tolist(),
            "checks": dict(self.checks),
        }


def orthonormalize_paired_directions(
    P: Any,
    Q: Any,
    *,
    pair_tol: float = 1.0e-12,
    max_pairs: int = MAX_INTERFACE_ROWS,
) -> PairedInterfaceBasis:
    """Apply deterministic two-pass complex Gram--Schmidt to paired columns.

    The input column order is authoritative (patch, singular-value, then
    original-mode order is supplied by the caller).  A column is accepted only
    when both independently normalized residual components exceed
    ``pair_tol``; this keeps the P/Q column counts paired for non-Hermitian
    problems.  Delta scaling, patch restriction and multiplicity weights are
    intentionally performed by the caller before this function.
    """

    if not np.isfinite(pair_tol) or pair_tol <= 0:
        raise ValueError("pair_tol must be positive and finite")
    if (
        not isinstance(max_pairs, (int, np.integer))
        or not 1 <= int(max_pairs) <= MAX_INTERFACE_ROWS
    ):
        raise ValueError("max_pairs must be between 1 and 512")
    P_array = _direction_matrix(P, name="P")
    Q_array = _direction_matrix(Q, name="Q")
    if P_array.shape != Q_array.shape:
        raise ValueError("paired P and Q must have the same shape")
    accepted: list[int] = []
    rejected: list[int] = []
    unprocessed: list[int] = []
    normalized_components: list[dict[str, float]] = []
    tiny = np.finfo(np.float64).tiny
    ambient_rows, candidate_count = (int(value) for value in P_array.shape)
    storage_capacity = min(int(max_pairs), candidate_count)
    P_storage = np.empty(
        (storage_capacity, ambient_rows), dtype=np.complex128
    )
    Q_storage = np.empty(
        (storage_capacity, ambient_rows), dtype=np.complex128
    )
    for column in range(P_array.shape[1]):
        p_work = P_array[:, column].copy()
        q_work = Q_array[:, column].copy()
        p_initial = max(tiny, float(np.linalg.norm(p_work)))
        q_initial = max(tiny, float(np.linalg.norm(q_work)))
        # The paired MGS test is defined on independently normalized input
        # candidates.  This also makes the acceptance residual dimensionless
        # without hiding a small candidate behind an absolute scale of one.
        p_work /= p_initial
        q_work /= q_initial
        for _pass in range(2):
            for basis_index in range(len(accepted)):
                p_basis = P_storage[basis_index]
                q_basis = Q_storage[basis_index]
                p_work -= np.vdot(p_basis, p_work) * p_basis
                q_work -= np.vdot(q_basis, q_work) * q_basis
        p_norm = float(np.linalg.norm(p_work))
        q_norm = float(np.linalg.norm(q_work))
        if not np.isfinite(p_norm) or not np.isfinite(q_norm):
            raise FloatingPointError("paired Gram--Schmidt produced a non-finite norm")
        # ``p_work`` and ``q_work`` have already been independently
        # normalized above.  The acceptance components are therefore the
        # dimensionless post-MGS norms themselves; dividing by the original
        # norm a second time would incorrectly favor small input columns.
        p_component = p_norm
        q_component = q_norm
        normalized_components.append(
            {
                "input_index": int(column),
                "p_component": p_component,
                "q_component": q_component,
            }
        )
        if p_component <= pair_tol or q_component <= pair_tol:
            rejected.append(column)
            continue
        accepted_index = len(accepted)
        P_storage[accepted_index] = p_work / p_norm
        Q_storage[accepted_index] = q_work / q_norm
        accepted.append(column)
        if len(accepted) == int(max_pairs):
            unprocessed.extend(range(column + 1, P_array.shape[1]))
            break
    if accepted:
        # The storage is allocated once and exposed as a correctly shaped
        # view; no second column_stack-sized P/Q library is created.
        P_out = P_storage[: len(accepted)].T
        Q_out = Q_storage[: len(accepted)].T
    else:
        P_out = np.empty((P_array.shape[0], 0), dtype=np.complex128)
        Q_out = np.empty((Q_array.shape[0], 0), dtype=np.complex128)
    if accepted:
        p_gram_error = float(
            np.linalg.norm(P_out.conj().T @ P_out - np.eye(len(accepted)))
        )
        q_gram_error = float(
            np.linalg.norm(Q_out.conj().T @ Q_out - np.eye(len(accepted)))
        )
    else:
        p_gram_error = q_gram_error = 0.0
    gram_scale = max(tiny, float(np.linalg.norm(np.eye(len(accepted)), ord="fro")))
    input_basis_bytes = int(P_array.nbytes + Q_array.nbytes)
    output_basis_capacity_bytes = int(P_storage.nbytes + Q_storage.nbytes)
    candidate_work_bytes = int(2 * ambient_rows * np.dtype(np.complex128).itemsize)
    # P_out/Q_out are views into the two storage arrays, but a contiguous
    # public-basis copy can coexist with all four raw/storage libraries while
    # the final Gram checks and identity hashes are evaluated.  Account for
    # that fifth full library and the small matrix/identity temporaries.
    public_basis_copy_bytes = int(
        ambient_rows * len(accepted) * np.dtype(np.complex128).itemsize
    )
    gram_identity_bytes = int(
        3 * len(accepted) * len(accepted) * np.dtype(np.complex128).itemsize
    )
    checks = {
        "two_pass_gram_schmidt": True,
        "pair_tolerance": float(pair_tol),
        "max_pairs": int(max_pairs),
        "accepted_rank": len(accepted),
        "rejected_count": len(rejected),
        "unprocessed_count": len(unprocessed),
        "unprocessed_indices": unprocessed,
        "accepted_limit_reached": bool(len(accepted) == int(max_pairs)),
        "p_euclidean_orthogonality": p_gram_error,
        "q_euclidean_orthogonality": q_gram_error,
        "p_subspace_gram_relative": p_gram_error / gram_scale,
        "q_subspace_gram_relative": q_gram_error / gram_scale,
        "normalized_components": normalized_components,
        "input_order_preserved": True,
        "reference_used": False,
        "p_sha256": _array_sha256(P_out),
        "q_sha256": _array_sha256(Q_out),
        "input_basis_bytes": input_basis_bytes,
        "output_basis_capacity_bytes": output_basis_capacity_bytes,
        "candidate_work_bytes": candidate_work_bytes,
        "public_basis_copy_bytes": public_basis_copy_bytes,
        "gram_identity_bytes": gram_identity_bytes,
        "workspace_bytes": int(
            input_basis_bytes
            + output_basis_capacity_bytes
            + candidate_work_bytes
            + public_basis_copy_bytes
            + gram_identity_bytes
        ),
    }
    if p_gram_error > 1.0e-10 or q_gram_error > 1.0e-10:
        raise FloatingPointError(f"paired two-pass Gram--Schmidt failed: {checks}")
    return PairedInterfaceBasis(
        P=P_out,
        Q=Q_out,
        accepted_indices=np.asarray(accepted, dtype=np.int64),
        rejected_indices=np.asarray(rejected, dtype=np.int64),
        unprocessed_indices=np.asarray(unprocessed, dtype=np.int64),
        checks=checks,
    )


@dataclass
class InterfaceCoarsePair:
    """The one small ``E = Q^H S P`` factor used by the fixed Q3 cycle."""

    P: np.ndarray
    Q: np.ndarray
    E: np.ndarray
    lu: np.ndarray
    pivots: np.ndarray
    facts: dict[str, Any]
    owns_basis: bool = False
    destroyed: bool = False

    @property
    def ambient_rows(self) -> int:
        return int(self.P.shape[0])

    @property
    def coarse_rows(self) -> int:
        return int(self.P.shape[1])

    def solve(self, rhs: Any) -> np.ndarray:
        if self.destroyed:
            raise RuntimeError("the Q3 coarse pair has been released")
        values = np.asarray(rhs, dtype=np.complex128)
        if values.ndim not in (1, 2) or values.shape[0] != self.coarse_rows:
            raise ValueError("coarse RHS has the wrong shape")
        if not np.all(np.isfinite(values)):
            raise ValueError("coarse RHS contains non-finite values")
        from scipy.linalg import lu_solve

        result = lu_solve((self.lu, self.pivots), values, check_finite=True)
        if not np.all(np.isfinite(result)):
            raise FloatingPointError("coarse solve returned non-finite values")
        result = np.ascontiguousarray(result)
        residual = self.E @ result - values
        rhs_norm = float(np.linalg.norm(values))
        relative_residual = float(
            np.linalg.norm(residual) / max(np.finfo(np.float64).tiny, rhs_norm)
        )
        if not np.isfinite(relative_residual):
            raise FloatingPointError("coarse solve residual is non-finite")
        solve_count = int(self.facts.get("solve_count", 0)) + 1
        previous_max = float(self.facts.get("max_solve_residual", 0.0))
        self.facts["solve_count"] = solve_count
        self.facts["last_solve_residual"] = relative_residual
        self.facts["max_solve_residual"] = max(previous_max, relative_residual)
        solve_gate = float(self.facts.get("solve_gate", 1.0e-10))
        if relative_residual > solve_gate:
            raise np.linalg.LinAlgError(
                "COARSE_PAIR_UNSTABLE: "
                f"solve residual={relative_residual:.17g} > {solve_gate:.17g}"
            )
        return result

    def apply(self, rhs: Any) -> np.ndarray:
        values = np.asarray(rhs, dtype=np.complex128)
        if values.ndim not in (1, 2) or values.shape[0] != self.ambient_rows:
            raise ValueError("interface RHS has the wrong shape")
        # Form Q^H values without materializing a conjugated/transposed copy
        # of the full Gamma-by-rank basis.  This is algebraically identical to
        # ``Q.conj().T @ values`` for vectors and blocks.
        coefficients = np.conjugate(self.Q.T @ np.conjugate(values))
        return np.ascontiguousarray(self.P @ self.solve(coefficients))

    def audit(self) -> dict[str, Any]:
        return {
            **self.facts,
            "basis_ownership": "owned" if self.owns_basis else "borrowed",
            "destroyed": bool(self.destroyed),
        }

    def destroy(self) -> None:
        if self.destroyed:
            return
        # P/Q are borrowed when the builder can retain the caller's contiguous
        # arrays.  Destruction only drops this object's references; it never
        # mutates or clears the caller-owned basis arrays.
        self.P = np.empty((0, 0), dtype=np.complex128)
        self.Q = np.empty((0, 0), dtype=np.complex128)
        self.E = np.empty((0, 0), dtype=np.complex128)
        self.lu = np.empty((0, 0), dtype=np.complex128)
        self.pivots = np.empty((0,), dtype=np.int64)
        self.destroyed = True


def build_interface_coarse_pair(
    S_gamma: Any,
    P: Any,
    Q: Any,
    *,
    max_rows: int = MAX_INTERFACE_ROWS,
    max_workspace_bytes: int = MAX_INTERFACE_WORKSPACE_BYTES,
    max_temp_workspace_bytes: int | None = None,
    rcond_rtol: float = 1.0e-12,
    solve_rtol: float = 1.0e-10,
) -> InterfaceCoarsePair:
    """Build and qualify exactly one small two-sided coarse pair.

    ``S_gamma`` must be a batch action callback or a sparse
    ``S_V``-plus-carrier action.  A dense global array is rejected, including
    small arrays used only as a convenient compatibility path, so the
    production interface cannot silently drift into a global dense matrix.
    Only the coarse ``E`` matrix and its LU are retained by the returned
    object.
    """

    if (
        not isinstance(max_rows, (int, np.integer))
        or not 1 <= int(max_rows) <= MAX_INTERFACE_ROWS
    ):
        raise ValueError("max_rows must be between 1 and 512")
    if not isinstance(max_workspace_bytes, (int, np.integer)) or int(max_workspace_bytes) <= 0:
        raise ValueError("max_workspace_bytes must be positive")
    if max_temp_workspace_bytes is None:
        max_temp_workspace_bytes = int(max_workspace_bytes)
    if (
        not isinstance(max_temp_workspace_bytes, (int, np.integer))
        or int(max_temp_workspace_bytes) <= 0
    ):
        raise ValueError("max_temp_workspace_bytes must be positive")
    if not np.isfinite(rcond_rtol) or rcond_rtol <= 0:
        raise ValueError("rcond_rtol must be positive and finite")
    if not np.isfinite(solve_rtol) or solve_rtol <= 0:
        raise ValueError("solve_rtol must be positive and finite")
    P_array = _direction_matrix(P, name="P")
    Q_array = _direction_matrix(Q, name="Q")
    if P_array.shape != Q_array.shape:
        raise ValueError("paired P and Q must have the same shape")
    coarse_rows = int(P_array.shape[1])
    if coarse_rows > int(max_rows):
        raise ValueError("Q3 coarse pair exceeds its row limit")
    if isinstance(S_gamma, np.ndarray) and S_gamma.ndim == 2:
        raise ValueError(
            "Q3 does not accept a dense global S_gamma; use a matrix-free "
            "action or the sparse S_V-plus-carrier action"
        )
    scalar_bytes = np.dtype(np.complex128).itemsize
    index_bytes = np.dtype(np.int64).itemsize
    # The 64 MiB contract applies to the small retained E/LU/probe lane.  The
    # transposed Q copy and a 32-column physical action are temporary vectors
    # in the shared 1 GiB pool, so they have a separate cap and ledger entry.
    coarse_factor_workspace_bound_bytes = int(
        3 * coarse_rows * coarse_rows * scalar_bytes
        + 3 * coarse_rows * scalar_bytes
        + coarse_rows * index_bytes
    )
    q_h_copy_bytes = int(P_array.shape[0] * coarse_rows * scalar_bytes)
    batch_columns = int(min(SCHUR_BATCH_COLUMNS, coarse_rows))
    # ``_operator_apply`` owns a copy of the input block while the physical
    # bridge owns the returned block.  Both long-vector blocks can therefore
    # be live together with the Q^H copy; a one-block estimate would undercount
    # the shared temporary lane.
    operator_input_copy_bytes = int(
        P_array.shape[0] * batch_columns * scalar_bytes
    )
    operator_output_bytes = int(
        P_array.shape[0] * batch_columns * scalar_bytes
    )
    batch_action_bytes = int(operator_input_copy_bytes + operator_output_bytes)
    coarse_temp_workspace_bound_bytes = int(
        q_h_copy_bytes + operator_input_copy_bytes + operator_output_bytes
    )
    if coarse_factor_workspace_bound_bytes > int(max_workspace_bytes):
        raise MemoryError(
            "COARSE_PAIR_WORKSPACE_EXCEEDED: "
            f"{coarse_factor_workspace_bound_bytes} > {int(max_workspace_bytes)} bytes"
        )
    if coarse_temp_workspace_bound_bytes > int(max_temp_workspace_bytes):
        raise MemoryError(
            "COARSE_PAIR_TEMP_WORKSPACE_EXCEEDED: "
            f"{coarse_temp_workspace_bound_bytes} > "
            f"{int(max_temp_workspace_bytes)} bytes"
        )
    E = np.empty((coarse_rows, coarse_rows), dtype=np.complex128)
    q_h = np.empty((coarse_rows, P_array.shape[0]), dtype=np.complex128)
    np.conjugate(Q_array.T, out=q_h)
    for start in range(0, coarse_rows, SCHUR_BATCH_COLUMNS):
        stop = min(start + SCHUR_BATCH_COLUMNS, coarse_rows)
        S_P_block = _operator_apply(
            S_gamma,
            P_array[:, start:stop],
            name="S_gamma",
        )
        E[:, start:stop] = q_h @ S_P_block
        del S_P_block
    del q_h
    if not np.all(np.isfinite(E)):
        raise FloatingPointError("Q3 coarse pair E is non-finite")
    from scipy.linalg import lu_solve
    from scipy.linalg.lapack import get_lapack_funcs

    getrf, gecon = get_lapack_funcs(("getrf", "gecon"), (E,))
    lu, pivots, factor_info = getrf(E, overwrite_a=False)
    if int(factor_info) != 0:
        raise np.linalg.LinAlgError(
            f"COARSE_PAIR_UNSTABLE: getrf info={int(factor_info)}"
        )
    anorm = float(np.linalg.norm(E, ord=1))
    if not np.isfinite(anorm):
        raise FloatingPointError("Q3 coarse pair E norm is non-finite")
    if anorm == 0.0:
        rcond = 0.0
        gecon_info = 0
    else:
        rcond, gecon_info = gecon(lu, anorm)
        rcond = float(rcond)
    if int(gecon_info) != 0 or not np.isfinite(rcond):
        rcond = 0.0
    if rcond < rcond_rtol:
        raise np.linalg.LinAlgError(
            f"COARSE_PAIR_UNSTABLE: rcond={rcond:.17g} < {rcond_rtol:.17g}"
        )
    pivots_array = np.asarray(pivots, dtype=np.int64)
    probe = np.ones(coarse_rows, dtype=np.complex128)
    probe[1::2] = 1.0 + 0.5j
    probe_solution = lu_solve((lu, pivots_array), probe, check_finite=True)
    probe_product = E @ probe_solution
    probe_residual = probe_product - probe
    factorization_residual = float(
        np.linalg.norm(probe_residual)
        / max(np.finfo(np.float64).tiny, float(np.linalg.norm(probe)))
    )
    retained_probe_workspace_bytes = int(
        probe.nbytes
        + probe_solution.nbytes
        + probe_product.nbytes
        + probe_residual.nbytes
    )
    # Keep the small factor/probe lane separate from the long-vector action
    # lane above.  In particular, do not charge q_h or the action blocks to
    # this 64 MiB E/LU/solve inventory a second time.
    workspace_bytes = int(
        E.nbytes
        + lu.nbytes
        + pivots_array.nbytes
        + retained_probe_workspace_bytes
    )
    if factorization_residual > solve_rtol:
        raise np.linalg.LinAlgError(
            "COARSE_PAIR_UNSTABLE: "
            f"factorization residual={factorization_residual:.17g} > {solve_rtol:.17g}"
        )
    facts = {
        "schema": "task039extra.v14.interface-coarse-pair.v1",
        "formula": "E=Q^H S_gamma P",
        "ambient_rows": int(P_array.shape[0]),
        "coarse_rows": coarse_rows,
        "rcond": rcond,
        "rcond_gate": float(rcond_rtol),
        "rcond_method": "scipy.linalg.lapack.gecon",
        "factorization_residual": factorization_residual,
        "solve_gate": float(solve_rtol),
        "workspace_bytes": workspace_bytes,
        "coarse_workspace_bound_bytes": coarse_factor_workspace_bound_bytes,
        "coarse_factor_workspace_bound_bytes": coarse_factor_workspace_bound_bytes,
        "coarse_temp_workspace_bound_bytes": coarse_temp_workspace_bound_bytes,
        "temp_workspace_cap_bytes": int(max_temp_workspace_bytes),
        "q_h_copy_bytes": q_h_copy_bytes,
        "batch_action_bytes": batch_action_bytes,
        "operator_input_copy_bytes": operator_input_copy_bytes,
        "operator_output_bytes": operator_output_bytes,
        "batch_action_columns": batch_columns,
        "retained_E_bytes": int(E.nbytes),
        "retained_LU_bytes": int(lu.nbytes),
        "retained_pivots_bytes": int(pivots_array.nbytes),
        "probe_workspace_bytes": retained_probe_workspace_bytes,
        "workspace_cap_bytes": int(max_workspace_bytes),
        "global_dense_schur_constructed": False,
        "reference_used": False,
        "factor_count": 1,
        "assembly_batch_columns": SCHUR_BATCH_COLUMNS,
        "full_S_P_retained": False,
        "basis_ownership": (
            "borrowed"
            if np.shares_memory(P_array, np.asarray(P))
            and np.shares_memory(Q_array, np.asarray(Q))
            else "normalized_copy"
        ),
        "p_sha256": _array_sha256(P_array),
        "q_sha256": _array_sha256(Q_array),
    }
    coarse_identity = np.eye(coarse_rows, dtype=np.complex128)
    coarse_gram_scale = max(
        np.finfo(np.float64).tiny,
        float(np.linalg.norm(coarse_identity, ord="fro")),
    )
    facts["p_subspace_gram_relative"] = float(
        np.linalg.norm(P_array.conj().T @ P_array - coarse_identity, ord="fro")
        / coarse_gram_scale
    )
    facts["q_subspace_gram_relative"] = float(
        np.linalg.norm(Q_array.conj().T @ Q_array - coarse_identity, ord="fro")
        / coarse_gram_scale
    )
    del probe, probe_solution, probe_product, probe_residual, coarse_identity
    return InterfaceCoarsePair(
        P=P_array,
        Q=Q_array,
        E=E,
        # scipy's native getrf layout is already accepted by lu_solve.  Keep
        # it; copying here would retain a second coarse LU for no numerical
        # benefit.
        lu=lu,
        pivots=pivots_array,
        facts=facts,
        owns_basis=not (
            np.shares_memory(P_array, np.asarray(P))
            and np.shares_memory(Q_array, np.asarray(Q))
        ),
    )


def apply_interface_cycle(
    rhs: Any,
    apply_s: Callable[[np.ndarray], Any],
    apply_local: Callable[[np.ndarray], Any],
    coarse_pair: InterfaceCoarsePair,
    *,
    output: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply exactly one fixed ``J -> C -> J`` interface cycle.

    ``apply_local`` is the already-qualified local patch smoother ``J`` and
    ``apply_s`` is the matrix-free physical interface Schur action.  No
    reference vector, KSP, recycling pool, or convergence loop is hidden in
    this function.  The returned residual norms are the two residuals needed
    by the cycle; a final ``S @ x`` action is deliberately left to the caller
    so the operation count stays explicit.
    """

    values = np.asarray(rhs, dtype=np.complex128).reshape(-1)
    if values.size != coarse_pair.ambient_rows or not np.all(np.isfinite(values)):
        raise ValueError("interface RHS has the wrong size or is non-finite")
    original = values.copy()

    def apply_vector(function: Callable[[np.ndarray], Any], vector: np.ndarray, name: str) -> np.ndarray:
        result = _as_complex_array(function(vector.copy())).reshape(-1)
        if result.size != vector.size or not np.all(np.isfinite(result)):
            raise ValueError(f"{name} returned an invalid vector")
        return result

    u = apply_vector(apply_local, original, "apply_local")
    first_residual = original - apply_vector(apply_s, u, "apply_s")
    v = u + coarse_pair.apply(first_residual)
    second_residual = original - apply_vector(apply_s, v, "apply_s")
    result = v + apply_vector(apply_local, second_residual, "apply_local")
    if output is not None:
        target = np.asarray(output, dtype=np.complex128)
        if target.shape != result.shape:
            raise ValueError("cycle output has the wrong shape")
        target[...] = result
        result = target
    facts = {
        "schema": "task039extra.v14.interface-cycle.v1",
        "formula": "u=Jg; v=u+C(g-Su); x=v+J(g-Sv)",
        "local_apply_count": 2,
        "schur_apply_count": 2,
        "coarse_apply_count": 1,
        "cycle_count": 1,
        "first_residual_norm": float(np.linalg.norm(first_residual)),
        "second_residual_norm": float(np.linalg.norm(second_residual)),
        "final_residual_norm": "not_available",
        "reference_used": False,
        "input_unchanged": bool(np.array_equal(values, original)),
    }
    return result, facts


@dataclass
class InterfaceFintAdapter:
    """Adapt one fixed interface cycle to the existing intermediate API.

    The adapter performs one exact I/Gamma RHS reduction, one ``J-C-J``
    Gamma cycle, and one internal recovery.  It deliberately does not create
    a KSP, run an inner iteration, or evaluate the native p4 residual; the
    caller that owns the native action performs that final diagnostic.
    """

    core: Any
    local_smoother: "InterfaceLocalSmoother"
    coarse_pair: InterfaceCoarsePair
    apply_count: int = 0
    destroyed: bool = False
    last_apply_facts: dict[str, Any] = field(default_factory=dict)
    solver_identity: str = "fixed_interface_cycle_approximate"

    @staticmethod
    def _factor_counts(core: Any) -> list[int]:
        return [
            int(getattr(item.factor, "solve_calls", 0))
            for item in core.internal
        ]

    def apply_with_facts(self, rhs: Any) -> tuple[Any, dict[str, Any]]:
        if self.destroyed:
            raise RuntimeError("the interface F_int adapter has been released")
        started = time.perf_counter()
        counts_before = self._factor_counts(self.core)
        local_solve_before = [
            int(patch.solve_count) for patch in self.local_smoother.patches
        ]
        coarse_solve_before = int(self.coarse_pair.facts.get("solve_count", 0))
        local_apply_before = int(self.local_smoother.apply_count)
        reduced, port_rhs = self.core.reduce(rhs)
        port_rhs = np.asarray(port_rhs, dtype=np.complex128)
        if np.linalg.norm(port_rhs) != 0.0:
            raise ValueError("interface F_int expects a zero auxiliary port RHS")

        def factor_delta(before: list[int]) -> list[int]:
            after = self._factor_counts(self.core)
            return [
                int(current - previous)
                for previous, current in zip(before, after, strict=True)
            ]

        phase_factor_deltas: dict[str, list[int]] = {
            "reduce": factor_delta(counts_before),
        }
        schur_call = 0

        def traced_schur(values: np.ndarray) -> np.ndarray:
            nonlocal schur_call
            before = self._factor_counts(self.core)
            result = self.core.apply_physical_schur_array(values)
            schur_call += 1
            phase_factor_deltas[f"S{schur_call}"] = factor_delta(before)
            return result

        local_call = 0

        def traced_local(values: np.ndarray) -> np.ndarray:
            nonlocal local_call
            result = self.local_smoother.apply(values)
            local_call += 1
            return result

        gamma_solution, cycle_facts = apply_interface_cycle(
            reduced,
            traced_schur,
            traced_local,
            self.coarse_pair,
        )
        before_recovery = self._factor_counts(self.core)
        result, recovery_facts = self.core.recover(
            rhs,
            gamma_solution,
            return_facts=True,
        )
        phase_factor_deltas["recover"] = factor_delta(before_recovery)
        counts_after = self._factor_counts(self.core)
        local_solve_after = [
            int(patch.solve_count) for patch in self.local_smoother.patches
        ]
        coarse_solve_after = int(self.coarse_pair.facts.get("solve_count", 0))
        local_apply_after = int(self.local_smoother.apply_count)
        factor_solve_delta = [
            int(after - before)
            for before, after in zip(counts_before, counts_after, strict=True)
        ]
        self.apply_count += 1
        facts = {
            "schema": "task039extra.v14.interface-fint-adapter.v1",
            "status": "INTERFACE_CYCLE_APPROXIMATE",
            "solver_identity": self.solver_identity,
            "formula": "reduce -> J-C-J -> recover",
            "reference_used": False,
            "ksp_created": False,
            "inner_iteration_count": 0,
            "native_residual": "not_available",
            "port_rhs_norm": float(np.linalg.norm(port_rhs)),
            "gamma_rhs_norm": float(np.linalg.norm(reduced)),
            "gamma_solution_norm": float(np.linalg.norm(gamma_solution)),
            "cycle": cycle_facts,
            "recovery": recovery_facts,
            "operation_counts": {
                "route": ["reduce", "J1", "S1", "E1", "S2", "J2", "recover"],
                "reduce_internal_solves": int(sum(phase_factor_deltas["reduce"])),
                "local_J1_apply_count": int(local_call >= 1),
                "S1_internal_solves": int(sum(phase_factor_deltas.get("S1", []))),
                "coarse_E1_apply_count": int(
                    coarse_solve_after - coarse_solve_before
                ),
                "S2_internal_solves": int(sum(phase_factor_deltas.get("S2", []))),
                "local_J2_apply_count": int(local_call >= 2),
                "recover_internal_solves": int(sum(phase_factor_deltas["recover"])),
                "factor_solve_delta_by_phase": phase_factor_deltas,
                "schur_action_count": int(schur_call),
                "local_action_count": int(local_call),
            },
            "factor_solve_counts_before": counts_before,
            "factor_solve_counts_after": counts_after,
            "factor_solve_delta": factor_solve_delta,
            "factor_solve_delta_total": int(sum(factor_solve_delta)),
            "factor_solve_delta_max_per_block": max(factor_solve_delta, default=0),
            "factor_solve_limit_per_block": 4,
            "factor_solve_limit_total": int(4 * len(counts_before)),
            "local_patch_solve_counts_before": local_solve_before,
            "local_patch_solve_counts_after": local_solve_after,
            "local_patch_solve_delta": [
                int(after - before)
                for before, after in zip(
                    local_solve_before, local_solve_after, strict=True
                )
            ],
            "local_patch_apply_count": int(
                sum(after - before for before, after in zip(
                    local_solve_before, local_solve_after, strict=True
                ))
            ),
            "local_patch_apply_count_total": int(sum(local_solve_after)),
            "local_smoother_apply_count": int(local_apply_after - local_apply_before),
            "local_smoother_apply_count_total": local_apply_after,
            "coarse_solve_count": int(coarse_solve_after - coarse_solve_before),
            "coarse_solve_count_total": coarse_solve_after,
            "apply_count": self.apply_count,
            "elapsed_seconds": time.perf_counter() - started,
            "finite": True,
        }
        self.last_apply_facts = facts
        return result, facts

    def solve_intermediate(self, rhs: Any, **_kwargs: Any) -> dict[str, Any]:
        """Return the caller-owned solution mapping for the fixed F_int route."""

        result, facts = self.apply_with_facts(rhs)
        return {"final_solution": result, **facts}

    def apply(self, rhs: Any) -> Any:
        return self.apply_with_facts(rhs)[0]

    __call__ = apply

    def destroy(self) -> None:
        self.core = None
        self.local_smoother = None
        self.coarse_pair = None
        self.destroyed = True


@dataclass
class InterfacePatchFactor:
    """One complete local ``S_i`` LU used by the interface smoother.

    The original dense ``S_i`` is retained beside its LU so every local
    backsolve can be checked against the unmodified physical block.  The
    builder still extracts and qualifies patches sequentially; this retained
    matrix library is explicit in the Q3 resident-inventory accounting.
    """

    patch_id: int | str
    rows: np.ndarray
    matrix: np.ndarray
    lu: np.ndarray
    pivots: np.ndarray
    output_weights: np.ndarray
    facts: dict[str, Any]
    solve_count: int = 0
    destroyed: bool = False

    def apply(self, rhs: Any) -> np.ndarray:
        if self.destroyed:
            raise RuntimeError("the local interface factor has been released")
        values = np.asarray(rhs, dtype=np.complex128)
        if values.ndim != 1 or values.shape != (self.rows.size,):
            raise ValueError("local interface RHS has the wrong shape")
        if not np.all(np.isfinite(values)):
            raise ValueError("local interface RHS contains non-finite values")
        from scipy.linalg import lu_solve

        solution = lu_solve((self.lu, self.pivots), values, check_finite=True)
        if not np.all(np.isfinite(solution)):
            raise FloatingPointError("local interface solve returned non-finite values")
        self.solve_count += 1
        self.facts["solve_count"] = int(self.solve_count)
        residual = self.matrix @ solution - values
        relative_residual = float(
            np.linalg.norm(residual)
            / max(np.finfo(np.float64).tiny, float(np.linalg.norm(values)))
        )
        if not np.isfinite(relative_residual):
            raise FloatingPointError("local interface solve residual is non-finite")
        self.facts["last_solve_residual"] = relative_residual
        self.facts["max_solve_residual"] = max(
            float(self.facts.get("max_solve_residual", 0.0)), relative_residual
        )
        solve_gate = float(self.facts.get("solve_gate", 1.0e-10))
        if relative_residual > solve_gate:
            raise np.linalg.LinAlgError(
                "LOCAL_PATCH_UNSTABLE: "
                f"solve residual={relative_residual:.17g} > {solve_gate:.17g}"
            )
        return np.ascontiguousarray(self.output_weights * solution)

    def audit(self) -> dict[str, Any]:
        return {**self.facts, "destroyed": bool(self.destroyed)}

    def destroy(self) -> None:
        if self.destroyed:
            return
        self.matrix = np.empty((0, 0), dtype=np.complex128)
        self.rows = np.empty((0,), dtype=np.int64)
        self.lu = np.empty((0, 0), dtype=np.complex128)
        self.pivots = np.empty((0,), dtype=np.int64)
        self.output_weights = np.empty((0,), dtype=np.float64)
        self.destroyed = True


@dataclass
class InterfaceLocalSmoother:
    """The additive complete-LU patch smoother ``J`` for one interface."""

    ambient_rows: int
    patches: list[InterfacePatchFactor]
    facts: dict[str, Any]
    paired_bases: dict[int, PairedPatchBasis] = field(default_factory=dict)
    apply_count: int = 0
    destroyed: bool = False

    def apply(self, rhs: Any, output: np.ndarray | None = None) -> np.ndarray:
        if self.destroyed:
            raise RuntimeError("the local interface smoother has been released")
        values = np.asarray(rhs, dtype=np.complex128)
        if values.ndim != 1 or values.shape != (self.ambient_rows,):
            raise ValueError("interface smoother RHS has the wrong shape")
        if not np.all(np.isfinite(values)):
            raise ValueError("interface smoother RHS contains non-finite values")
        result = np.zeros(self.ambient_rows, dtype=np.complex128)
        for patch in self.patches:
            result[patch.rows] += patch.apply(values[patch.rows])
        if output is not None:
            target = np.asarray(output, dtype=np.complex128)
            if target.shape != result.shape:
                raise ValueError("interface smoother output has the wrong shape")
            target[...] = result
            result = target
        self.apply_count += 1
        self.facts["apply_count"] = int(self.apply_count)
        return result

    __call__ = apply

    def audit(self) -> dict[str, Any]:
        return {
            **self.facts,
            "apply_count": int(self.apply_count),
            "patches": [patch.audit() for patch in self.patches],
            "paired_bases": {
                str(patch_id): basis.audit()
                for patch_id, basis in self.paired_bases.items()
            },
            "destroyed": bool(self.destroyed),
        }

    def destroy(self) -> None:
        if self.destroyed:
            return
        for patch in self.patches:
            patch.destroy()
        self.patches.clear()
        self.paired_bases.clear()
        self.destroyed = True


def _dense_lu_probe(
    matrix: np.ndarray,
    *,
    solve_rtol: float,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Factor one local dense matrix with LAPACK ``getrf/gecon`` checks."""

    from scipy.linalg import lu_solve
    from scipy.linalg.lapack import get_lapack_funcs

    getrf, gecon = get_lapack_funcs(("getrf", "gecon"), (matrix,))
    lu, pivots, factor_info = getrf(matrix, overwrite_a=False)
    if int(factor_info) != 0:
        raise np.linalg.LinAlgError(
            f"LOCAL_PATCH_UNSTABLE: getrf info={int(factor_info)}"
        )
    anorm = float(np.linalg.norm(matrix, ord=1))
    if not np.isfinite(anorm):
        raise FloatingPointError("local patch matrix norm is non-finite")
    if anorm == 0.0:
        rcond = 0.0
        gecon_info = 0
    else:
        try:
            rcond, gecon_info = gecon(lu, anorm)
            rcond = float(rcond)
            gecon_info = int(gecon_info)
        except Exception:
            # The local rcond is diagnostic only.  Local acceptance is based
            # on successful factorization and the explicit original-S_i
            # solve residual below; a failed condition estimate is recorded
            # without inventing a second local stability gate.
            rcond = None
            gecon_info = None
    if rcond is not None and not np.isfinite(rcond):
        rcond = None
    pivots_array = np.asarray(pivots, dtype=np.int64)
    probe = np.ones(matrix.shape[0], dtype=np.complex128)
    probe[1::2] = 1.0 + 0.5j
    probe_solution = lu_solve((lu, pivots_array), probe, check_finite=True)
    probe_product = matrix @ probe_solution
    probe_residual = probe_product - probe
    residual = float(
        np.linalg.norm(probe_residual)
        / max(np.finfo(np.float64).tiny, float(np.linalg.norm(probe)))
    )
    workspace_bytes = int(
        matrix.nbytes
        + lu.nbytes
        + probe.nbytes
        + probe_solution.nbytes
        + probe_product.nbytes
        + probe_residual.nbytes
        + pivots_array.nbytes
    )
    facts = {
        "rcond": rcond,
        "rcond_gecon_info": gecon_info,
        "rcond_gate": None,
        "rcond_gate_applied": False,
        "rcond_method": "scipy.linalg.lapack.gecon",
        "factorization_residual": residual,
        "solve_gate": float(solve_rtol),
        "workspace_bytes": workspace_bytes,
        "matrix_sha256": _array_sha256(matrix),
    }
    del probe, probe_solution, probe_product, probe_residual
    if residual > float(solve_rtol):
        raise np.linalg.LinAlgError(
            "LOCAL_PATCH_UNSTABLE: "
            f"factorization residual={residual:.17g} > {solve_rtol:.17g}"
        )
    # Keep LAPACK's native factor layout.  ``lu_solve`` accepts it directly;
    # making a C-contiguous copy here would retain a duplicate of every local
    # LU in the resident smoother inventory.
    return lu, pivots_array, facts


def _seed_block_rows_from_geometry(
    space: Any,
    floquet: Any,
) -> tuple[int, np.ndarray, tuple[np.ndarray, ...]]:
    """Recreate the canonical 42 full p4 seed supports from the native map."""

    dofmap, slaves, links = _mpc_storage_map(space, floquet)
    storage_size = max(
        int(dofmap.max()) + 1,
        int(getattr(space.dofmap.index_map, "size_global", 0)),
    )
    slave_set = set(slaves.tolist())
    cell_active: list[np.ndarray] = []
    for cell in dofmap:
        expanded: list[int] = []
        for dof in cell:
            dof = int(dof)
            expanded.extend(
                links.get(dof, np.asarray([dof], dtype=np.int64)).tolist()
            )
        cell_active.append(
            np.asarray(sorted(set(expanded) - slave_set), dtype=np.int64)
        )
    groups = _cell_seed_groups(space.mesh, len(cell_active))
    block_rows: list[np.ndarray] = []
    for cells in groups:
        block_rows.append(
            np.asarray(
                sorted(
                    set(
                        np.concatenate(
                            [cell_active[int(cell)] for cell in cells]
                        ).tolist()
                    )
                ),
                dtype=np.int64,
            )
        )
    if len(block_rows) != 42 or any(not rows.size for rows in block_rows):
        raise ValueError("canonical p4 geometry did not produce 42 nonempty seed supports")
    return storage_size, np.sort(slaves), tuple(block_rows)


def interface_patch_rows_from_core(
    core: Any,
    space: Any,
    floquet: Any,
) -> tuple[np.ndarray, ...]:
    """Return canonical seed-support/Gamma intersections in compact Gamma rows."""

    storage_size, _slaves, seed_rows = _seed_block_rows_from_geometry(space, floquet)
    if storage_size != int(core.partition.storage_size):
        raise ValueError("canonical seed support storage size differs from Schur core")
    gamma_full = np.asarray(core.partition.gamma_full_indices, dtype=np.int64)
    gamma_position = {int(row): index for index, row in enumerate(gamma_full)}
    rows: list[np.ndarray] = []
    for patch_id, seed in enumerate(seed_rows):
        values = np.asarray(
            sorted(
                gamma_position[int(row)]
                for row in seed
                if int(row) in gamma_position
            ),
            dtype=np.int64,
        )
        if values.size == 0:
            raise ValueError(f"canonical interface patch {patch_id} has no Gamma rows")
        rows.append(np.ascontiguousarray(values))
    covered = np.unique(np.concatenate(rows))
    expected = np.arange(gamma_full.size, dtype=np.int64)
    if not np.array_equal(covered, expected):
        raise ValueError("canonical seed-support/Gamma intersections do not cover Gamma")
    return tuple(rows)


def _local_physical_schur_matrix(
    volume_schur: Any,
    rows: np.ndarray,
    port_data: Iterable[Mapping[str, Any]],
) -> np.ndarray:
    """Extract one local ``S_V+B H^-1 D`` block without a global dense copy."""

    if not hasattr(volume_schur, "getValues"):
        raise TypeError("local patch extraction requires a sparse PETSc S_V action")
    matrix = np.asarray(
        volume_schur.getValues(rows.tolist(), rows.tolist()),
        dtype=np.complex128,
    )
    if matrix.shape != (rows.size, rows.size):
        raise ValueError("sparse S_V returned an incompatible local patch block")
    positions = {int(value): index for index, value in enumerate(rows)}
    for entry in port_data:
        h = complex(entry["normalization_h"])
        if h == 0.0:
            raise ZeroDivisionError("port normalization H is zero")
        b_rows = np.asarray(entry["b_gamma"], dtype=np.int64).reshape(-1)
        b_values = np.asarray(entry["b_values"], dtype=np.complex128).reshape(-1)
        d_rows = np.asarray(entry["d_gamma"], dtype=np.int64).reshape(-1)
        d_values = np.asarray(entry["d_values"], dtype=np.complex128).reshape(-1)
        for b_row, b_value in zip(b_rows, b_values, strict=True):
            local_row = positions.get(int(b_row))
            if local_row is None:
                continue
            for d_row, d_value in zip(d_rows, d_values, strict=True):
                local_column = positions.get(int(d_row))
                if local_column is not None:
                    matrix[local_row, local_column] += b_value * d_value / h
    if not np.all(np.isfinite(matrix)):
        raise FloatingPointError("local physical Schur patch is non-finite")
    return np.ascontiguousarray(matrix)


def build_interface_local_smoother(
    volume_schur: Any,
    patch_rows: Iterable[Any],
    *,
    port_data: Iterable[Mapping[str, Any]] = (),
    ambient_rows: int | None = None,
    max_rows: int = MAX_INTERNAL_ROWS,
    max_workspace_bytes: int = 512 * 1024**2,
    paired_basis_workspace_bytes: int = 1 << 30,
    solve_rtol: float = 1.0e-10,
    paired_patch_deltas: Mapping[int, Any] | None = None,
    process_order: Iterable[int] | None = None,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> InterfaceLocalSmoother:
    """Build complete local ``S_i`` LU factors and the additive smoother ``J``.

    Patches are extracted and qualified sequentially.  The current
    construction workspace is bounded before extraction, while the returned
    smoother deliberately retains each original ``S_i`` matrix, its LU, row
    map and ``1/multiplicity`` output weights for real solve checks.
    Representative patch SVDs, when requested, use that same live matrix
    before it is transferred into the retained patch object.
    """

    if (
        not isinstance(max_rows, (int, np.integer))
        or not 1 <= int(max_rows) <= MAX_INTERNAL_ROWS
    ):
        raise ValueError("local patch max_rows must be between 1 and 2048")
    if not isinstance(max_workspace_bytes, (int, np.integer)) or int(max_workspace_bytes) <= 0:
        raise ValueError("local patch workspace cap must be positive")
    if (
        not isinstance(paired_basis_workspace_bytes, (int, np.integer))
        or int(paired_basis_workspace_bytes) <= 0
    ):
        raise ValueError("paired basis workspace cap must be positive")
    if not np.isfinite(solve_rtol) or solve_rtol <= 0:
        raise ValueError("local patch solve_rtol must be positive and finite")
    if isinstance(volume_schur, np.ndarray) and volume_schur.ndim == 2:
        raise ValueError("local physical patches require sparse S_V, not a global dense matrix")
    if ambient_rows is None:
        get_size = getattr(volume_schur, "getSize", None)
        shape = getattr(volume_schur, "shape", None)
        if callable(get_size):
            ambient_rows = int(get_size()[0])
        elif shape is not None and len(shape) == 2:
            ambient_rows = int(shape[0])
        else:
            raise ValueError("ambient_rows is required for this sparse S_V action")
    ambient_rows = int(ambient_rows)
    if ambient_rows <= 0:
        raise ValueError("local smoother ambient_rows must be positive")
    rows_list: list[np.ndarray] = []
    for patch_id, raw_rows in enumerate(patch_rows):
        rows = np.asarray(raw_rows, dtype=np.int64).reshape(-1)
        if rows.size == 0 or np.unique(rows).size != rows.size:
            raise ValueError(f"interface patch {patch_id} has duplicate or empty rows")
        if np.any(rows < 0) or np.any(rows >= ambient_rows):
            raise ValueError(f"interface patch {patch_id} is outside Gamma")
        if rows.size > int(max_rows):
            raise ValueError("Q3 local patch exceeds the 2048-row limit")
        rows_list.append(np.ascontiguousarray(rows))
    if not rows_list:
        raise ValueError("local smoother requires at least one patch")
    multiplicity = np.zeros(ambient_rows, dtype=np.int64)
    for rows in rows_list:
        multiplicity[rows] += 1
    port_data_tuple = tuple(port_data)
    paired_patch_deltas = (
        {}
        if paired_patch_deltas is None
        else {int(patch_id): value for patch_id, value in paired_patch_deltas.items()}
    )
    if any(
        not isinstance(patch_id, (int, np.integer))
        or int(patch_id) < 0
        or int(patch_id) >= len(rows_list)
        for patch_id in paired_patch_deltas
    ):
        raise ValueError("paired patch delta keys must identify local patches")
    if process_order is None:
        processing_order = tuple(range(len(rows_list)))
    else:
        processing_order = tuple(int(patch_id) for patch_id in process_order)
        if sorted(processing_order) != list(range(len(rows_list))):
            raise ValueError(
                "process_order must contain every local patch exactly once"
            )
    patches: list[InterfacePatchFactor] = []
    paired_bases: dict[int, PairedPatchBasis] = {}
    temporary_peak_bytes = 0
    retained_factor_bytes = 0
    retained_matrix_bytes = 0
    retained_lu_bytes = 0
    retained_paired_basis_bytes = 0
    progress_records: list[dict[str, Any]] = []
    build_started = time.perf_counter()
    scalar_bytes = np.dtype(np.complex128).itemsize
    index_bytes = np.dtype(np.int64).itemsize

    def notify_progress(
        event: str,
        patch_id: int,
        ordinal: int,
        *,
        rows_count: int,
        workspace_bound: int,
        paired_svd_bound: int = 0,
        facts: Mapping[str, Any] | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "event": str(event),
            "patch_id": int(patch_id),
            "ordinal": int(ordinal),
            "patch_count": len(rows_list),
            "rows": int(rows_count),
            "elapsed_seconds": time.perf_counter() - build_started,
            "workspace_bound_bytes": int(workspace_bound),
            "paired_svd_workspace_bound_bytes": int(paired_svd_bound),
        }
        if facts is not None:
            record["patch_facts"] = dict(facts)
        progress_records.append(record)
        if progress_callback is not None:
            progress_callback(dict(record))

    try:
        for ordinal, patch_id in enumerate(processing_order, start=1):
            rows = rows_list[patch_id]
            rows_count = int(rows.size)
            workspace_bound = int(
                3 * rows_count * rows_count * scalar_bytes
                + 3 * rows_count * scalar_bytes
                + rows_count * index_bytes
            )
            if workspace_bound > int(max_workspace_bytes):
                raise MemoryError(
                    "LOCAL_PATCH_WORKSPACE_EXCEEDED: "
                    f"{workspace_bound} > {int(max_workspace_bytes)} bytes"
                )
            paired_svd_bound = (
                int(12 * rows_count * rows_count * scalar_bytes
                    + 8 * rows_count * scalar_bytes)
                if patch_id in paired_patch_deltas
                else 0
            )
            if paired_svd_bound > int(paired_basis_workspace_bytes):
                raise MemoryError(
                    "PAIRED_PATCH_SVD_WORKSPACE_EXCEEDED: "
                    f"{paired_svd_bound} > {int(paired_basis_workspace_bytes)} bytes"
                )
            notify_progress(
                "patch_started",
                patch_id,
                ordinal,
                rows_count=rows_count,
                workspace_bound=workspace_bound,
                paired_svd_bound=paired_svd_bound,
            )
            matrix = _local_physical_schur_matrix(
                volume_schur,
                rows,
                port_data_tuple,
            )
            lu, pivots, facts = _dense_lu_probe(
                matrix,
                solve_rtol=solve_rtol,
            )
            paired_basis_seconds = 0.0
            if patch_id in paired_patch_deltas:
                paired_started = time.perf_counter()
                paired_basis = build_paired_patch_basis(
                    matrix,
                    paired_patch_deltas[patch_id],
                    patch_id=patch_id,
                    max_workspace_bytes=int(paired_basis_workspace_bytes),
                )
                paired_basis_seconds = time.perf_counter() - paired_started
                paired_bases[int(patch_id)] = paired_basis
                retained_paired_basis_bytes += int(
                    paired_basis.P.nbytes
                    + paired_basis.Q.nbytes
                    + paired_basis.singular_values.nbytes
                )
            temporary_peak_bytes = max(
                temporary_peak_bytes,
                int(max(workspace_bound, facts["workspace_bytes"])),
            )
            if patch_id in paired_bases:
                temporary_peak_bytes = max(
                    temporary_peak_bytes,
                    int(paired_bases[patch_id].checks["svd_workspace_bytes"]),
                )
            weights = np.ascontiguousarray(1.0 / multiplicity[rows])
            facts.update(
                {
                    "patch_id": patch_id,
                    "rows": rows_count,
                    "row_sha256": _array_sha256(rows),
                    "output_weight_definition": "1/multiplicity",
                    "multiplicity_min": int(np.min(multiplicity[rows])),
                    "multiplicity_max": int(np.max(multiplicity[rows])),
                    "workspace_bound_bytes": workspace_bound,
                    "paired_basis_seconds": paired_basis_seconds,
                    "matrix_bytes": int(matrix.nbytes),
                    "lu_bytes": int(lu.nbytes),
                    "pivots_bytes": int(pivots.nbytes),
                }
            )
            patches.append(
                InterfacePatchFactor(
                    patch_id=patch_id,
                    rows=rows,
                    matrix=matrix,
                    lu=lu,
                    pivots=pivots,
                    output_weights=weights,
                    facts=facts,
                )
            )
            retained_factor_bytes += int(
                matrix.nbytes
                + lu.nbytes
                + pivots.nbytes
                + rows.nbytes
                + weights.nbytes
            )
            retained_matrix_bytes += int(matrix.nbytes)
            retained_lu_bytes += int(lu.nbytes)
            notify_progress(
                "patch_completed",
                patch_id,
                ordinal,
                rows_count=rows_count,
                workspace_bound=workspace_bound,
                paired_svd_bound=paired_svd_bound,
                facts=facts,
            )
    except BaseException:
        for patch in patches:
            patch.destroy()
        raise
    uncovered_rows = np.flatnonzero(multiplicity == 0).astype(np.int64)
    facts = {
        "schema": "task039extra.v14.interface-local-smoother.v1",
        "formula": "Jr=sum_i R_i^H W_i S_i^-1 R_i r",
        "ambient_rows": ambient_rows,
        "patch_count": len(patches),
        "all_local_factors_complete": True,
        "max_patch_rows": max(int(rows.size) for rows in rows_list),
        "multiplicity_min": int(np.min(multiplicity[multiplicity > 0])),
        "multiplicity_max": int(np.max(multiplicity)),
        "uncovered_rows": int(uncovered_rows.size),
        "uncovered_row_sha256": _array_sha256(uncovered_rows),
        "temporary_peak_workspace_bytes": temporary_peak_bytes,
        "processing_order": [int(patch_id) for patch_id in processing_order],
        "progress": progress_records,
        "build_elapsed_seconds": time.perf_counter() - build_started,
        "retained_matrix_bytes": retained_matrix_bytes,
        "retained_lu_bytes": retained_lu_bytes,
        "retained_factor_bytes": retained_factor_bytes,
        "retained_paired_basis_bytes": retained_paired_basis_bytes,
        "retained_resident_bytes": int(
            retained_factor_bytes + retained_paired_basis_bytes
        ),
        "local_factor_workspace_cap_bytes": int(max_workspace_bytes),
        "paired_basis_workspace_cap_bytes": int(paired_basis_workspace_bytes),
        "rcond_gate": None,
        "rcond_gate_applied": False,
        "solve_gate": float(solve_rtol),
        "paired_patch_ids": sorted(paired_bases),
        "paired_basis_count": len(paired_bases),
        "reference_used": False,
    }
    return InterfaceLocalSmoother(
        ambient_rows=ambient_rows,
        patches=patches,
        facts=facts,
        paired_bases=paired_bases,
    )


def build_port_direction_families(
    port_data: Iterable[Mapping[str, Any]],
    delta: Any,
    ambient_rows: int,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Build all ``Delta^-1 B`` and ``Delta^-1 conjugate(D)^T`` candidates."""

    ambient_rows = int(ambient_rows)
    if ambient_rows <= 0:
        raise ValueError("port direction ambient_rows must be positive")
    delta_array = np.asarray(delta, dtype=np.complex128).reshape(-1)
    if delta_array.size != ambient_rows or not np.all(np.isfinite(delta_array)):
        raise ValueError("port direction Delta has the wrong shape or is non-finite")
    if np.any(np.abs(delta_array.imag) > 1.0e-14) or np.any(delta_array.real <= 0):
        raise ValueError("port direction Delta must be real and positive")
    delta_inv = 1.0 / delta_array.real
    entries = tuple(port_data)
    if not entries:
        raise ValueError("physical interface has no port direction families")
    direction_count = 2 * len(entries)
    P = np.empty((ambient_rows, direction_count), dtype=np.complex128)
    Q = np.empty_like(P)
    mapping: list[dict[str, Any]] = []
    column = 0
    for entry in entries:
        b_rows = np.asarray(entry["b_gamma"], dtype=np.int64).reshape(-1)
        b_values = np.asarray(entry["b_values"], dtype=np.complex128).reshape(-1)
        if b_rows.size != b_values.size or np.any(b_rows < 0) or np.any(b_rows >= ambient_rows):
            raise ValueError("port B family has an invalid support")
        P[:, column] = 0.0
        np.add.at(P[:, column], b_rows, delta_inv[b_rows] * b_values)
        Q[:, column] = P[:, column]
        mapping.append(
            {
                "family": "B",
                "port": int(entry["port"]),
                "source": "Delta^-1_b_m",
            }
        )
        column += 1
        d_rows = np.asarray(entry["d_gamma"], dtype=np.int64).reshape(-1)
        d_values = np.asarray(entry["d_values"], dtype=np.complex128).reshape(-1)
        if d_rows.size != d_values.size or np.any(d_rows < 0) or np.any(d_rows >= ambient_rows):
            raise ValueError("port conjugate-D family has an invalid support")
        P[:, column] = 0.0
        np.add.at(P[:, column], d_rows, delta_inv[d_rows] * np.conjugate(d_values))
        Q[:, column] = P[:, column]
        mapping.append(
            {
                "family": "conjugate_D",
                "port": int(entry["port"]),
                "source": "Delta^-1_conjugate(d_m)^T",
            }
        )
        column += 1
    # The non-Hermitian candidate pair intentionally retains independent P/Q
    # storage even though these carrier-generated seed columns start equal.
    return P, Q, mapping


def build_interface_candidate_directions(
    patch_rows: Iterable[Any],
    paired_bases: Mapping[int, PairedPatchBasis],
    port_data: Iterable[Mapping[str, Any]],
    delta_gamma: Any,
    *,
    max_candidates: int = 496,
    max_mgs_rows: int = MAX_INTERFACE_ROWS,
    preallocation_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    """Lift all local paired bases and both physical port direction families.

    This is the solver-owned candidate construction for Q3.  The callback is
    invoked before any port or raw P/Q array is allocated.  Its facts cover
    the simultaneous candidate-build peak, the two-pass MGS output library,
    and the later Q-transpose/32-column coarse-action temporaries so the
    runner can reserve the shared workspace once for the complete lane.
    """

    rows_tuple = tuple(
        np.asarray(rows, dtype=np.int64).reshape(-1) for rows in patch_rows
    )
    if not rows_tuple or any(rows.size == 0 for rows in rows_tuple):
        raise ValueError("interface candidate construction needs nonempty patches")
    delta_array = np.asarray(delta_gamma, dtype=np.complex128).reshape(-1)
    gamma_rows = int(delta_array.size)
    if gamma_rows <= 0 or not np.all(np.isfinite(delta_array)):
        raise ValueError("candidate Delta has the wrong shape or is non-finite")
    if np.any(np.abs(delta_array.imag) > 1.0e-14) or np.any(delta_array.real <= 0):
        raise ValueError("candidate Delta must be real and positive")
    if (
        not isinstance(max_candidates, (int, np.integer))
        or not 1 <= int(max_candidates) <= MAX_INTERFACE_ROWS
    ):
        raise ValueError("max_candidates must be between 1 and 512")
    if (
        not isinstance(max_mgs_rows, (int, np.integer))
        or not 1 <= int(max_mgs_rows) <= MAX_INTERFACE_ROWS
    ):
        raise ValueError("max_mgs_rows must be between 1 and 512")

    multiplicity = np.zeros(gamma_rows, dtype=np.int64)
    for rows in rows_tuple:
        if np.unique(rows).size != rows.size or np.any(rows < 0) or np.any(rows >= gamma_rows):
            raise ValueError("interface candidate patch has invalid Gamma rows")
        multiplicity[rows] += 1
    if np.any(multiplicity == 0):
        raise ValueError("interface candidate patches do not cover every Gamma row")

    normalized_bases: dict[int, PairedPatchBasis] = {}
    local_count = 0
    for raw_patch_id, basis in paired_bases.items():
        patch_id = int(raw_patch_id)
        if patch_id < 0 or patch_id >= len(rows_tuple):
            raise ValueError("paired basis identifies an invalid interface patch")
        if not isinstance(basis, PairedPatchBasis):
            raise TypeError("paired_bases must contain PairedPatchBasis objects")
        if basis.P.shape != (rows_tuple[patch_id].size, basis.rank):
            raise ValueError("paired right basis shape does not match its patch")
        if basis.Q.shape != basis.P.shape or basis.rank > 8:
            raise ValueError("paired left basis shape or rank is invalid")
        normalized_bases[patch_id] = basis
        local_count += int(basis.rank)
    entries = tuple(port_data)
    port_count = 2 * len(entries)
    candidate_count = int(local_count + port_count)
    candidate_upper_bound = int(len(rows_tuple) * 8 + port_count)
    if candidate_count <= 0:
        raise ValueError("Q3 candidate pair is empty")
    if candidate_count > candidate_upper_bound or candidate_count > int(max_candidates):
        raise ValueError("Q3 candidate pair exceeds its fixed column bound")

    scalar_bytes = np.dtype(np.complex128).itemsize
    raw_P_bytes = int(gamma_rows * candidate_count * scalar_bytes)
    raw_Q_bytes = raw_P_bytes
    port_output_bytes = int(gamma_rows * port_count * scalar_bytes * 2)
    # build_port_direction_families writes directly into its two output
    # arrays.  Only the current support products are transient; no list of
    # full-length port columns is retained.
    port_temporary_bytes = int(4 * gamma_rows * scalar_bytes)
    mgs_output_capacity = int(min(int(max_mgs_rows), candidate_count))
    mgs_output_basis_bytes = int(
        2 * gamma_rows * mgs_output_capacity * scalar_bytes
    )
    mgs_work_bytes = int(2 * gamma_rows * scalar_bytes)
    # The public P/Q views are backed by the row-major storage libraries, but
    # the final Gram checks and the two identity hashes may materialize one
    # additional full basis copy while all four input/storage libraries are
    # still live.  Keep that fifth-library peak in the shared workspace fact.
    public_basis_copy_bytes = int(
        gamma_rows * mgs_output_capacity * scalar_bytes
    )
    gram_identity_bytes = int(
        3 * mgs_output_capacity * mgs_output_capacity * scalar_bytes
    )
    mgs_peak_bytes = int(
        raw_P_bytes
        + raw_Q_bytes
        + mgs_output_basis_bytes
        + mgs_work_bytes
        + public_basis_copy_bytes
        + gram_identity_bytes
    )
    candidate_build_peak_bytes = int(
        raw_P_bytes + raw_Q_bytes + port_output_bytes + port_temporary_bytes
    )
    q_h_copy_bytes = int(gamma_rows * mgs_output_capacity * scalar_bytes)
    coarse_batch_columns = int(min(SCHUR_BATCH_COLUMNS, mgs_output_capacity))
    # The coarse action keeps the copied input block and the bridge-produced
    # output block live at the same time.  Count both in the same shared
    # workspace reservation as the Q^H copy.
    coarse_operator_input_bytes = int(
        gamma_rows * coarse_batch_columns * scalar_bytes
    )
    coarse_operator_output_bytes = int(
        gamma_rows * coarse_batch_columns * scalar_bytes
    )
    coarse_batch_action_bytes = int(
        coarse_operator_input_bytes + coarse_operator_output_bytes
    )
    coarse_temporary_bytes = int(
        q_h_copy_bytes
        + coarse_operator_input_bytes
        + coarse_operator_output_bytes
    )
    workspace_upper_bytes = int(
        max(candidate_build_peak_bytes, mgs_peak_bytes, coarse_temporary_bytes)
    )
    facts: dict[str, Any] = {
        "schema": "task039extra.v14.interface-candidate-directions.v1",
        "gamma_rows": gamma_rows,
        "local_candidate_count": int(local_count),
        "port_candidate_count": int(port_count),
        "candidate_count": candidate_count,
        "candidate_upper_bound": candidate_upper_bound,
        "max_candidates": int(max_candidates),
        "multiplicity_min": int(np.min(multiplicity)),
        "multiplicity_max": int(np.max(multiplicity)),
        "output_weight_definition": "1/multiplicity for local SVD directions only",
        "port_weight_applied": False,
        "raw_P_bytes": raw_P_bytes,
        "raw_Q_bytes": raw_Q_bytes,
        "port_output_bytes": port_output_bytes,
        "port_column_library_bytes": 0,
        "port_temporary_bytes": port_temporary_bytes,
        "mgs_output_basis_capacity_bytes": mgs_output_basis_bytes,
        "mgs_work_bytes": mgs_work_bytes,
        "public_basis_copy_bytes": public_basis_copy_bytes,
        "gram_identity_bytes": gram_identity_bytes,
        "mgs_peak_bytes": mgs_peak_bytes,
        "candidate_build_peak_bytes": candidate_build_peak_bytes,
        "q_h_copy_bytes": q_h_copy_bytes,
        "coarse_batch_action_bytes": coarse_batch_action_bytes,
        "coarse_operator_input_bytes": coarse_operator_input_bytes,
        "coarse_operator_output_bytes": coarse_operator_output_bytes,
        "coarse_batch_columns": coarse_batch_columns,
        "coarse_temporary_bytes": coarse_temporary_bytes,
        "workspace_upper_bytes": workspace_upper_bytes,
        "all_42_local_bases_required": len(normalized_bases) == len(rows_tuple),
        "paired_patch_ids": sorted(normalized_bases),
    }
    if preallocation_callback is not None:
        preallocation_callback(dict(facts))

    port_p, port_q, port_mapping = build_port_direction_families(
        entries, delta_array, gamma_rows
    )
    P = np.empty((gamma_rows, candidate_count), dtype=np.complex128)
    Q = np.empty_like(P)
    mapping: list[dict[str, Any]] = []
    output_weights = 1.0 / multiplicity.astype(np.float64)
    column = 0
    try:
        for patch_id in sorted(normalized_bases):
            basis = normalized_bases[patch_id]
            rows = rows_tuple[patch_id]
            for singular_index in range(basis.rank):
                P[:, column] = 0.0
                Q[:, column] = 0.0
                P[rows, column] = output_weights[rows] * basis.P[:, singular_index]
                Q[rows, column] = output_weights[rows] * basis.Q[:, singular_index]
                mapping.append(
                    {
                        "source": "local_svd",
                        "patch": int(patch_id),
                        "singular_index": int(singular_index),
                    }
                )
                column += 1
        P[:, column:] = port_p
        Q[:, column:] = port_q
        mapping.extend(port_mapping)
    finally:
        del port_p, port_q, multiplicity, output_weights
    if column + port_count != candidate_count or len(mapping) != candidate_count:
        raise RuntimeError("Q3 candidate mapping width is inconsistent")
    facts.update(
        {
            "input_P_bytes": int(P.nbytes),
            "input_Q_bytes": int(Q.nbytes),
            "port_P_bytes": int(port_output_bytes // 2),
            "port_Q_bytes": int(port_output_bytes // 2),
            "mapping_count": len(mapping),
            "all_42_local_bases": len(normalized_bases) == len(rows_tuple),
        }
    )
    return P, Q, mapping, facts




@dataclass(frozen=True)
class SchurPartition:
    """Compact active-index partition and its auditable full-storage identity."""

    storage_size: int
    active_full_indices: np.ndarray
    slave_full_indices: np.ndarray
    gamma_full_indices: np.ndarray
    gamma_active_indices: np.ndarray
    internal_blocks_full: tuple[np.ndarray, ...]
    internal_blocks_active: tuple[np.ndarray, ...]
    seed_group_count: int
    port_support_full_indices: np.ndarray
    cross_owner_volume_pairs: int = 0

    @property
    def active_rows(self) -> int:
        return int(self.active_full_indices.size)

    @property
    def gamma_rows(self) -> int:
        return int(self.gamma_active_indices.size)

    @property
    def internal_rows(self) -> int:
        return int(sum(block.size for block in self.internal_blocks_active))

    def audit(self) -> dict[str, Any]:
        sizes = [int(block.size) for block in self.internal_blocks_active]
        return {
            "schema": SCHUR_SCHEMA,
            "storage_rows": self.storage_size,
            "active_rows": self.active_rows,
            "slave_rows": int(self.slave_full_indices.size),
            "gamma_rows": self.gamma_rows,
            "internal_rows": self.internal_rows,
            "internal_block_count": len(self.internal_blocks_active),
            "internal_block_sizes": sizes,
            "max_internal_block_rows": max(sizes, default=0),
            "seed_group_count": self.seed_group_count,
            "port_support_rows": int(self.port_support_full_indices.size),
            "cross_owner_volume_pairs": int(self.cross_owner_volume_pairs),
            "partition_complete": self.active_rows == self.gamma_rows + self.internal_rows,
        }


def _mpc_storage_map(
    space: Any,
    floquet: Any,
) -> tuple[np.ndarray, np.ndarray, dict[int, np.ndarray]]:
    """Expand cell dofs through MPC links without constructing a macro object."""

    from .condensed_fine_reference import native_map_arrays

    mapping = native_map_arrays(space, floquet)
    dofmap = np.asarray(mapping["dofmap"], dtype=np.int64)
    slaves = np.asarray(mapping["slaves"], dtype=np.int64)
    masters = np.asarray(mapping["masters"], dtype=np.int64)
    coefficients = np.asarray(mapping["coefficients"], dtype=np.complex128)
    offsets = np.asarray(mapping["offsets"], dtype=np.int64)
    independent = np.asarray(mapping["independent_indices"], dtype=np.int64)
    storage_size = offsets.size - 1
    if storage_size <= 0 or independent.size + slaves.size != storage_size:
        raise ValueError("native p4 map has inconsistent storage/active sizes")
    if (
        offsets[0] != 0
        or offsets[-1] != masters.size
        or masters.size != coefficients.size
        or np.any(np.diff(offsets) < 0)
        or np.any(slaves < 0)
        or np.any(slaves >= storage_size)
        or np.any(masters < 0)
        or np.any(masters >= storage_size)
        or np.unique(slaves).size != slaves.size
        or np.intersect1d(slaves, masters).size
        or not np.array_equal(
            np.sort(independent),
            np.setdiff1d(np.arange(storage_size), np.unique(slaves)),
        )
    ):
        raise ValueError("native p4 MPC map failed the active-index identity gate")
    links: dict[int, np.ndarray] = {}
    for slave in slaves:
        start, stop = int(offsets[slave]), int(offsets[slave + 1])
        links[int(slave)] = masters[start:stop].copy()
    return dofmap, slaves, links


def _cell_seed_groups(mesh: Any, cell_count: int) -> list[np.ndarray]:
    geometry_dofmap = np.asarray(mesh.geometry.dofmap, dtype=np.int64)
    coordinates = np.asarray(mesh.geometry.x)
    if geometry_dofmap.shape[0] != cell_count:
        raise ValueError("geometry and function-space cell counts differ")
    minima = np.asarray(
        [
            coordinates[geometry_dofmap[cell]].min(axis=0)
            for cell in range(cell_count)
        ]
    )
    axes = [np.unique(minima[:, axis]) for axis in range(3)]
    if cell_count != 252 or tuple(len(axis) for axis in axes) != (6, 3, 14):
        raise ValueError(
            "frozen p4 geometry must contain 252 cells with 6x3x14 starts"
        )
    axis_indices = [
        np.searchsorted(axes[axis], minima[:, axis]) for axis in range(3)
    ]
    groups: dict[tuple[int, int, int], list[int]] = {}
    for cell in range(cell_count):
        key = tuple(int(axis_indices[axis][cell]) // 2 for axis in range(3))
        groups.setdefault(key, []).append(cell)
    return [
        np.asarray(groups[key], dtype=np.int64)
        for key in sorted(groups)
    ]


def _carrier_support(
    carrier: Any,
    storage_size: int,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    support: set[int] = set()
    port_data: list[dict[str, Any]] = []
    for port, entry in enumerate(carrier.entries):
        b_rows = np.asarray(entry.coupling_rows, dtype=np.int64).reshape(-1)
        b_values = np.asarray(entry.coupling_values, dtype=np.complex128).reshape(-1)
        d_rows = np.asarray(entry.projection_rows, dtype=np.int64).reshape(-1)
        d_values = np.asarray(entry.projection_values, dtype=np.complex128).reshape(-1)
        if b_rows.size != b_values.size or d_rows.size != d_values.size:
            raise ValueError(f"port {port} coupling/projection lengths differ")
        if (
            np.any(b_rows < 0)
            or np.any(b_rows >= storage_size)
            or np.any(d_rows < 0)
            or np.any(d_rows >= storage_size)
        ):
            raise ValueError(f"port {port} support is outside the p4 storage layout")
        b_keep = _nonzero_rows(b_values)
        d_keep = _nonzero_rows(d_values)
        support.update(b_rows[b_keep].tolist())
        support.update(d_rows[d_keep].tolist())
        port_data.append(
            {
                "port": port,
                "coupling_rows": b_rows,
                "coupling_values": b_values,
                "projection_rows": d_rows,
                "projection_values": d_values,
                "normalization_h": complex(entry.normalization_h),
            }
        )
    return np.asarray(sorted(support), dtype=np.int64), port_data


def build_interface_partition(
    space: Any,
    floquet: Any,
    carrier: Any,
    *,
    volume: Any | None = None,
) -> tuple[SchurPartition, list[dict[str, Any]]]:
    """Build the 42-cell p4 partition from geometry, MPC and port support.

    Only the reusable cell grouping and active-index rules are reproduced
    here.  No historical macro data structure is instantiated.
    """

    storage_size, slaves, block_rows = _seed_block_rows_from_geometry(space, floquet)
    slave_set = set(slaves.tolist())
    owners: dict[int, set[int]] = {}
    for owner, rows in enumerate(block_rows):
        for row in rows:
            owners.setdefault(int(row), set()).add(owner)
    active = np.asarray(
        [row for row in range(storage_size) if row not in slave_set],
        dtype=np.int64,
    )
    if set(np.concatenate(block_rows).tolist()) != set(active.tolist()):
        raise ValueError(
            "cell/MPC expansion does not cover exactly the legal active p4 rows"
        )
    support, port_data = _carrier_support(carrier, storage_size)
    if np.intersect1d(support, slaves).size:
        raise ValueError("port support contains an MPC slave row")
    gamma = set(support.tolist())
    gamma.update(
        row for row, row_owners in owners.items() if len(row_owners) > 1
    )
    cross_pairs = 0
    if volume is not None:
        owner_for_row = {
            row: next(iter(row_owners))
            for row, row_owners in owners.items()
            if len(row_owners) == 1 and row not in gamma
        }
        for row in active:
            row = int(row)
            if row not in owner_for_row:
                continue
            columns, _values = volume.getRow(row)
            for column in np.asarray(columns, dtype=np.int64):
                column = int(column)
                if column not in owner_for_row or column == row:
                    continue
                if owner_for_row[column] != owner_for_row[row]:
                    cross_pairs += 1
        if cross_pairs:
            raise ValueError(
                "nonzero volume coupling crosses two internal owners; "
                "Gamma must not be enlarged after the frozen partition gate"
            )
    gamma_full = np.asarray(sorted(gamma), dtype=np.int64)
    active_to_compact = -np.ones(storage_size, dtype=np.int64)
    active_to_compact[active] = np.arange(active.size, dtype=np.int64)
    gamma_active = active_to_compact[gamma_full]
    if np.any(gamma_active < 0):
        raise ValueError("Gamma contains an inactive row")
    gamma_active = np.sort(gamma_active)
    gamma_set = set(gamma_full.tolist())
    blocks_full = tuple(
        np.asarray(
            [row for row in rows if int(row) not in gamma_set],
            dtype=np.int64,
        )
        for rows in block_rows
    )
    blocks_active = tuple(active_to_compact[rows] for rows in blocks_full)
    if any(np.any(block < 0) for block in blocks_active):
        raise ValueError("internal block contains an inactive row")
    partition = SchurPartition(
        storage_size=storage_size,
        active_full_indices=active,
        slave_full_indices=np.sort(slaves),
        gamma_full_indices=gamma_full,
        gamma_active_indices=gamma_active,
        internal_blocks_full=blocks_full,
        internal_blocks_active=blocks_active,
        seed_group_count=len(block_rows),
        port_support_full_indices=support,
        cross_owner_volume_pairs=cross_pairs,
    )
    audit = partition.audit()
    if not audit["partition_complete"] or partition.seed_group_count != 42:
        raise ValueError(f"unexpected p4 interface partition: {audit}")
    if partition.storage_size == 53084 and (
        partition.active_rows != 48960
        or partition.gamma_rows != 13092
        or partition.internal_rows != 35868
    ):
        raise ValueError(
            "frozen p4 partition changed: expected active=48960, "
            "Gamma=13092, internal=35868"
        )
    if any(block.size == 0 or block.size > MAX_INTERNAL_ROWS for block in blocks_active):
        raise ValueError("frozen p4 internal blocks must be nonempty and <=2048 rows")
    return partition, port_data

 
 
@dataclass
class InternalFactor:
    block_index: int
    indices: np.ndarray
    matrix: Any
    factor: Any
    grows: np.ndarray
    gcols: np.ndarray
    A_gi: np.ndarray
    A_i_g: np.ndarray
    symbolic_raw: dict[str, Any]
    numeric_raw: dict[str, Any]
    memory_request: dict[str, Any]
    symbolic_seconds: float
    numeric_seconds: float
    solve_calls_at_build: int = 0
 
 
@dataclass
class PhysicalInterfaceSchur:
    """Owned sparse Schur matrices and live internal/interface factors."""
 
    volume: Any
    partition: SchurPartition
    S_V: Any
    V_GG: Any
    interface_matrix: Any
    internal: list[InternalFactor]
    interface_factor: Any
    port_data: list[dict[str, Any]]
    factor_facts: dict[str, Any] = field(default_factory=dict)
    owns_volume: bool = True
    destroyed: bool = False
 
    def _solve_factor(self, item: InternalFactor, values: np.ndarray) -> np.ndarray:
        rhs = item.matrix.createVecRight()
        solution = item.matrix.createVecRight()
        try:
            rhs.array[:] = values
            item.factor.solve_repeated(rhs, solution)
            return np.asarray(solution.array).copy()
        finally:
            rhs.destroy()
            solution.destroy()
 
    def _interface_solve(self, values: np.ndarray) -> np.ndarray:
        if self.interface_factor is None:
            raise RuntimeError("the global interface factor has not been built")
        rhs = self.interface_matrix.createVecRight()
        solution = self.interface_matrix.createVecRight()
        try:
            rhs.array[:] = values
            self.interface_factor.solve_repeated(rhs, solution)
            return np.asarray(solution.array).copy()
        finally:
            rhs.destroy()
            solution.destroy()

    def _reduce_rhs(
        self,
        rhs: Any,
        port_rhs: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        input_array = _as_complex_array(rhs)
        if input_array.size != self.partition.storage_size:
            raise ValueError("Schur reduction expects full p4 storage RHS")
        active_rhs = np.asarray(
            input_array[self.partition.active_full_indices],
            dtype=np.complex128,
        )
        gamma = self.partition.gamma_active_indices
        reduced = active_rhs[gamma].copy()
        for item in self.internal:
            local_rhs = active_rhs[item.indices]
            if item.grows.size:
                reduced[item.grows] -= item.A_gi @ self._solve_factor(
                    item, local_rhs
                )
        ports = len(self.port_data)
        port_values = (
            np.zeros(ports, dtype=np.complex128)
            if port_rhs is None
            else np.asarray(port_rhs, dtype=np.complex128)
        )
        if port_values.shape != (ports,):
            raise ValueError("port RHS has the wrong shape")
        return active_rhs, reduced, port_values

    def reduce(
        self,
        rhs: Any,
        *,
        port_rhs: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return the exact ``[g_G-A_GI A_II^-1 g_I; g_port]`` RHS."""

        _active_rhs, reduced, port_values = self._reduce_rhs(rhs, port_rhs)
        return reduced, port_values
 
    def solve(
        self,
        rhs: Any,
        *,
        port_rhs: np.ndarray | None = None,
        return_facts: bool = False,
    ) -> Any:
        """Eliminate all ``I_i``, solve one interface system, then recover."""
 
        active_rhs, reduced, port_values = self._reduce_rhs(rhs, port_rhs)
        gamma = self.partition.gamma_active_indices
        interface_solution = self._interface_solve(
            np.concatenate((reduced, port_values))
        )
        result, recovery_facts = self.recover(
            rhs,
            interface_solution[: gamma.size],
            return_facts=True,
        )
        output = _as_complex_array(result)
        facts = {
            **recovery_facts,
            "volume_rhs_norm": float(np.linalg.norm(active_rhs)),
            "interface_rhs_norm": float(
                np.linalg.norm(np.concatenate((reduced, port_values)))
            ),
            "internal_elimination_solves": len(self.internal),
            "interface_solves": 1,
            "interface_solution": interface_solution.copy(),
            "slave_solution_max": float(
                np.max(np.abs(output[self.partition.slave_full_indices]), initial=0.0)
            ),
        }
        return (result, facts) if return_facts else result

    def recover(
        self,
        rhs: Any,
        gamma_solution: Any,
        *,
        return_facts: bool = False,
    ) -> Any:
        """Recover internal p4 values from a supplied interface solution.

        This path only needs the retained local factors and ``V_GI`` blocks;
        it remains valid after the explicit ``S_V`` and global interface
        factor have been released.
        """

        input_array = _as_complex_array(rhs)
        if input_array.size != self.partition.storage_size:
            raise ValueError("Schur recovery expects full p4 storage RHS")
        gamma_solution = _as_complex_array(gamma_solution)
        if gamma_solution.size != self.partition.gamma_rows:
            raise ValueError("Gamma solution has the wrong size")
        active_rhs = np.asarray(
            input_array[self.partition.active_full_indices],
            dtype=np.complex128,
        )
        active_solution = np.zeros(self.partition.active_rows, dtype=np.complex128)
        active_solution[self.partition.gamma_active_indices] = gamma_solution
        for item in self.internal:
            rhs_local = active_rhs[item.indices].copy()
            if item.gcols.size:
                rhs_local -= item.A_i_g @ active_solution[
                    self.partition.gamma_active_indices[item.gcols]
                ]
            active_solution[item.indices] = self._solve_factor(item, rhs_local)
        output = np.zeros(self.partition.storage_size, dtype=np.complex128)
        output[self.partition.active_full_indices] = active_solution
        if hasattr(rhs, "duplicate"):
            result = rhs.duplicate()
            result.set(0)
            result.array[:] = output
        else:
            result = output
        facts = {
            "internal_recovery_solves": len(self.internal),
            "slave_solution_max": float(
                np.max(np.abs(output[self.partition.slave_full_indices]), initial=0.0)
            ),
        }
        return (result, facts) if return_facts else result
 
    def apply_volume_schur(self, vector: Any, output: Any | None = None) -> Any:
        """Apply ``S_V = V_GG - sum(V_GI V_II^-1 V_IG)`` matrix-free."""
 
        if hasattr(vector, "duplicate"):
            target = self.V_GG.createVecLeft() if output is None else output
            self.V_GG.mult(vector, target)
            for item in self.internal:
                if item.grows.size and item.gcols.size:
                    target.array[item.grows] -= item.A_gi @ self._solve_factor(
                        item,
                        item.A_i_g @ np.asarray(vector.array[item.gcols]),
                    )
            return target
        raise TypeError("the production Schur action requires a PETSc Vec")

    def apply_physical_schur(self, vector: Any, output: Any | None = None) -> Any:
        """Apply ``S = S_V + B H^-1 D`` without retaining a port matrix."""

        if not hasattr(vector, "array"):
            raise TypeError("the production physical Schur action requires a PETSc Vec")
        target = self.V_GG.createVecLeft() if output is None else output
        self.apply_volume_schur(vector, target)
        values = np.asarray(vector.array)
        for entry in self.port_data:
            h = entry["normalization_h"]
            if h == 0:
                raise ZeroDivisionError("port normalization H is zero")
            port_value = np.dot(
                entry["d_values"], values[entry["d_gamma"]]
            ) / h
            target.array[entry["b_gamma"]] += entry["b_values"] * port_value
        return target

    def apply_physical_schur_block(
        self,
        values: Any,
        output: np.ndarray | None = None,
    ) -> np.ndarray:
        """Apply the physical ``S_Gamma`` to a two-dimensional column block.

        This is the explicit PETSc bridge used by Q3 coarse assembly.  One
        pair of PETSc vectors is reused for every supplied column; the bridge
        does not create a dense global Schur matrix or retain ``S @ P``.
        """

        if self.destroyed or self.V_GG is None:
            raise RuntimeError("the physical interface Schur has been released")
        block = np.asarray(values, dtype=np.complex128)
        if block.ndim != 2 or block.shape[0] != self.partition.gamma_rows:
            raise ValueError("physical Schur block has the wrong shape")
        if block.shape[1] == 0 or not np.all(np.isfinite(block)):
            raise ValueError("physical Schur block must be nonempty and finite")
        if output is None:
            target_array = np.empty_like(block)
        else:
            target_array = np.asarray(output, dtype=np.complex128)
            if target_array.shape != block.shape:
                raise ValueError("physical Schur block output has the wrong shape")
        source = self.V_GG.createVecRight()
        target = self.V_GG.createVecLeft()
        try:
            for column in range(block.shape[1]):
                source.array[:] = block[:, column]
                self.apply_physical_schur(source, target)
                target_array[:, column] = target.array
        finally:
            source.destroy()
            target.destroy()
        if not np.all(np.isfinite(target_array)):
            raise FloatingPointError("physical Schur block action returned non-finite values")
        return np.ascontiguousarray(target_array)

    def apply_physical_schur_array(self, values: Any) -> np.ndarray:
        """Apply the physical Schur to one Gamma vector as a NumPy array."""

        vector = np.asarray(values, dtype=np.complex128).reshape(-1)
        if vector.size != self.partition.gamma_rows:
            raise ValueError("physical Schur array has the wrong size")
        return self.apply_physical_schur_block(vector[:, None])[:, 0]
 
    def apply_volume_schur_adjoint(self, vector: Any, output: Any | None = None) -> Any:
        """Apply the conjugate-transpose Schur operator using each same factor."""
 
        if not hasattr(vector, "array"):
            raise TypeError("the production adjoint Schur action requires a PETSc Vec")
        target = self.V_GG.createVecLeft() if output is None else output
        self.V_GG.multHermitian(vector, target)
        for item in self.internal:
            if not item.grows.size or not item.gcols.size:
                continue
            rhs = item.matrix.createVecRight()
            solution = item.matrix.createVecRight()
            try:
                rhs.array[:] = item.A_gi.conj().T @ np.asarray(vector.array[item.grows])
                solve_adjoint = getattr(item.factor, "solve_adjoint", None)
                if not callable(solve_adjoint):
                    raise RuntimeError("the live factor has no adjoint solve API")
                solve_adjoint(rhs, solution)
                target.array[item.gcols] -= item.A_i_g.conj().T @ np.asarray(
                    solution.array
                )
            finally:
                rhs.destroy()
                solution.destroy()
        return target

    def apply_physical_schur_adjoint(
        self,
        vector: Any,
        output: Any | None = None,
    ) -> Any:
        """Apply ``S.H = S_V.H + D.H H^{-H} B.H`` with the same factors."""

        if not hasattr(vector, "array"):
            raise TypeError(
                "the production physical adjoint action requires a PETSc Vec"
            )
        target = self.V_GG.createVecLeft() if output is None else output
        self.apply_volume_schur_adjoint(vector, target)
        values = np.asarray(vector.array)
        for entry in self.port_data:
            h = entry["normalization_h"]
            if h == 0:
                raise ZeroDivisionError("port normalization H is zero")
            port_value = np.dot(
                np.conj(entry["b_values"]), values[entry["b_gamma"]]
            ) / np.conj(h)
            target.array[entry["d_gamma"]] += np.conj(
                entry["d_values"]
            ) * port_value
        return target
 
    def apply_interface_matrix_free(self, vector: Any, output: Any | None = None) -> Any:
        """Apply the assembled augmented interface matrix by its blocks."""

        if not hasattr(vector, "array"):
            raise TypeError("the production interface action requires a PETSc Vec")
        values = np.asarray(vector.array)
        target = (
            self.interface_matrix.createVecLeft() if output is None else output
        )
        target.set(0)
        gamma_size = self.partition.gamma_rows
        volume_input = self.V_GG.createVecRight()
        volume_input.array[:] = values[:gamma_size]
        volume_output = self.V_GG.createVecLeft()
        try:
            self.apply_volume_schur(volume_input, volume_output)
            target.array[:gamma_size] = volume_output.array
        finally:
            volume_input.destroy()
            volume_output.destroy()
        for port, entry in enumerate(self.port_data):
            target.array[entry["b_gamma"]] += (
                entry["b_values"] * values[gamma_size + port]
            )
            target.array[gamma_size + port] -= np.dot(
                entry["d_values"], values[entry["d_gamma"]]
            )
            target.array[gamma_size + port] += (
                entry["normalization_h"] * values[gamma_size + port]
            )
        return target
 
    def destroy(self) -> None:
        if self.destroyed:
            return
        _destroy(self.interface_factor)
        self.interface_factor = None
        for item in self.internal:
            _destroy(item.factor)
            _destroy(item.matrix)
        self.internal.clear()
        for value in (self.interface_matrix, self.S_V, self.V_GG):
            _destroy(value)
        self.release_owned_volume()
        self.interface_matrix = self.S_V = self.V_GG = None
        self.volume = None
        self.destroyed = True

    def release_owned_volume(self) -> None:
        """Release the owned active-volume matrix while keeping Schur state.

        The explicit ``S_V`` and matrix-free state retain all data needed for
        later local-action, reduction, recovery, and physical-Schur checks.
        A borrowed volume remains owned by the caller and is left untouched.
        The ownership flag is cleared after release so later cleanup is
        idempotent.
        """

        if not self.owns_volume:
            return
        _destroy(self.volume)
        self.volume = None
        self.owns_volume = False

    def release_explicit_schur(self) -> None:
        """Release global/interface matrices while preserving recovery state.

        The optional global interface factor, assembled ``S_V``, augmented
        interface matrix, and owned active volume are released.  The local
        internal factors, their coupling blocks, ``V_GG`` and port data stay
        live so the recovered physical action remains available for the
        controlled post-factor memory phase.
        """

        self.release_global_factor()
        _destroy(self.S_V)
        self.S_V = None
        _destroy(self.interface_matrix)
        self.interface_matrix = None
        self.release_owned_volume()

    def release_global_factor(self) -> None:
        """Release the optional global interface numeric factor only."""

        _destroy(self.interface_factor)
        self.interface_factor = None
 
 
def _petsc_is(PETSc: Any, indices: np.ndarray, comm: Any) -> Any:
    return PETSc.IS().createGeneral(
        np.asarray(indices, dtype=PETSc.IntType), comm=comm
    )
 
 
def _submatrix(matrix: Any, rows: np.ndarray) -> Any:
    from petsc4py import PETSc
 
    row_is = _petsc_is(PETSc, rows, matrix.getComm())
    col_is = _petsc_is(PETSc, rows, matrix.getComm())
    try:
        return matrix.createSubMatrix(row_is, col_is)
    finally:
        row_is.destroy()
        col_is.destroy()
 
 
def _csr_adjacency(matrix: Any) -> list[np.ndarray]:
    try:
        indptr, indices, _values = matrix.getValuesCSR()
        return [
            np.asarray(indices[indptr[row] : indptr[row + 1]])
            for row in range(len(indptr) - 1)
        ]
    except (AttributeError, RuntimeError, TypeError):
        rows: list[np.ndarray] = []
        for row in range(int(matrix.getSize()[0])):
            columns, _values = matrix.getRow(row)
            rows.append(np.asarray(columns).copy())
        return rows
 
 
def _prepare_factor(
    matrix: Any,
    factor_factory: Callable[[Any], Any],
    *,
    label: str,
    resource_sample: Callable[[], Mapping[str, Any]] | None = None,
    marker: Callable[[str, Mapping[str, Any]], None] | None = None,
    pre_numeric_gate: Callable[[Mapping[str, Any]], None] | None = None,
    post_numeric_gate: Callable[[Mapping[str, Any]], None] | None = None,
    inventory_components: Mapping[str, int]
    | Callable[[Mapping[str, Any]], Mapping[str, int]]
    | None = None,
    memory_request_builder: Callable[[Mapping[str, Any], Any], Mapping[str, Any]]
    | None = None,
    numeric_observer: Callable[[Mapping[str, Any]], None] | None = None,
) -> tuple[Any, dict[str, Any]]:
    def sample() -> dict[str, Any] | None:
        return dict(resource_sample()) if resource_sample is not None else None

    def emit(stage: str, facts: Mapping[str, Any]) -> None:
        if marker is not None:
            marker(stage, dict(facts))

    def inventory(facts: Mapping[str, Any]) -> dict[str, int]:
        if inventory_components is None:
            return {}
        values = (
            inventory_components(facts)
            if callable(inventory_components)
            else inventory_components
        )
        return {str(key): int(value) for key, value in values.items()}

    factor = factor_factory(matrix)
    blr_memory_mode = str(getattr(factor, "profile", "")) in {
        "physical_p4_blr_bal_h_v16",
        "physical_p4_blr_tradeoff_v17",
        "physical_p4_cell_condensed_blr_v18",
    }
    info_indices = (9, 22, 29, 35, 36, 37) if blr_memory_mode else (22, 29)
    # The opt-in observer receives the complete native record used by the
    # reviewed factor evidence, including the extended INFOG(29/35/36/37)
    # fields.  The historical path still queries only ``info_indices``.
    observer_info_indices = tuple(
        dict.fromkeys((*info_indices, 9, 19, 22, 29, 35, 36, 37))
    )
    matrix_facts = {
        "label": label,
        "rows": int(matrix.getSize()[0]),
        "matrix_info_before_factor": matrix.getInfo(),
        "pre_factor_resource": sample(),
    }
    emit("schur_factor_symbolic_started", matrix_facts)
    try:
        symbolic_started = time.perf_counter()
        factor.symbolic(matrix)
        symbolic_seconds = time.perf_counter() - symbolic_started
        symbolic_raw = factor.info(info_indices)
        memory_request = v11_memory_request_mb(symbolic_raw, blr=blr_memory_mode)
        set_memory_limit = getattr(factor, "set_memory_limit_mb", None)
        if not callable(set_memory_limit):
            raise RuntimeError("V11 factor does not expose ICNTL(23) memory setting")
        settings_getter = getattr(factor, "symbolic_memory_settings", None)
        settings = settings_getter() if callable(settings_getter) else None
        emit(
            "schur_factor_symbolic_complete",
            {
                **matrix_facts,
                "symbolic_raw": symbolic_raw,
                "symbolic_memory_settings": settings,
                "symbolic_resource": sample(),
            },
        )
        if memory_request_builder is not None:
            # Only the explicitly opted-in caller may replace the V11 request.
            # Keep the old request as prediction evidence, not backend input.
            legacy_request = memory_request
            memory_request = dict(memory_request_builder({
                **matrix_facts,
                "symbolic_raw": symbolic_raw,
                "symbolic_memory_settings": settings,
                "symbolic_seconds": symbolic_seconds,
                "symbolic_resource": sample(),
                "legacy_v11_memory_request": legacy_request,
            }, factor))
            requested = memory_request.get("requested_memory_limit_mb")
            if type(requested) is not int or requested <= 0:
                raise ValueError("explicit MUMPS quota must be positive decimal MB")
            memory_request["legacy_v11_memory_request"] = legacy_request
        set_memory_limit(memory_request["requested_memory_limit_mb"])
        get_memory_limit = getattr(factor, "get_icntl", None)
        if not callable(get_memory_limit):
            raise RuntimeError("V11 factor does not expose ICNTL(23) readback")
        memory_readback = int(get_memory_limit(23))
        if memory_readback != int(memory_request["requested_memory_limit_mb"]):
            raise RuntimeError(
                "V11 ICNTL(23) readback differs from the requested memory package"
            )
        settings_after = settings_getter() if callable(settings_getter) else None
        if settings is not None and settings_after is not None:
            before_icntl = dict(settings.get("icntl", {}))
            after_icntl = dict(settings_after.get("icntl", {}))
            changed = {
                key: (before_icntl.get(key), after_icntl.get(key))
                for key in set(before_icntl) | set(after_icntl)
                if key != "23" and before_icntl.get(key) != after_icntl.get(key)
            }
            if changed:
                raise RuntimeError(f"V11 changed a non-memory MUMPS control: {changed}")
        symbolic_facts = {
            **matrix_facts,
            "symbolic_raw": symbolic_raw,
            "symbolic_memory_settings": settings,
            "symbolic_memory_settings_after_memory_limit": settings_after,
            "memory_request": memory_request,
            "icntl23_readback_mb": memory_readback,
            "symbolic_seconds": symbolic_seconds,
            "symbolic_resource": sample(),
        }
        backend_controls = getattr(factor, "blr_control_facts", None)
        if backend_controls is not None:
            symbolic_facts["backend_control_facts"] = dict(backend_controls)
        symbolic_facts["inventory_components"] = inventory(symbolic_facts)
        if pre_numeric_gate is not None:
            pre_numeric_gate(symbolic_facts)
        emit(
            "schur_factor_numeric_started",
            symbolic_facts,
        )
        numeric_started = time.perf_counter()
        try:
            factor.numeric(matrix)
        except BaseException as error:
            if numeric_observer is not None:
                failure_raw = None
                info_error = None
                try:
                    failure_raw = factor.info(observer_info_indices)
                except BaseException as query_error:
                    info_error = f"{type(query_error).__name__}: {query_error}"
                observation = {
                    **symbolic_facts,
                    "numeric_completed": False,
                    "numeric_seconds": time.perf_counter() - numeric_started,
                    "numeric_raw": failure_raw,
                    "numeric_info_error": info_error,
                    "numeric_exception": f"{type(error).__name__}: {error}",
                    "factor_solve_calls_at_factorization": int(
                        getattr(factor, "solve_calls", 0)
                    ),
                }
                numeric_observer(observation)
                emit("schur_factor_numeric_failed", observation)
            raise
        numeric_seconds = time.perf_counter() - numeric_started
        numeric_raw = factor.info(
            observer_info_indices if numeric_observer is not None else info_indices
        )
        if numeric_observer is not None:
            error_code = numeric_raw["infog"].get("1")
            observation = {
                **symbolic_facts,
                "numeric_call_returned": True,
                "numeric_completed": type(error_code) is int and error_code >= 0,
                "numeric_seconds": numeric_seconds,
                "numeric_raw": numeric_raw,
                "matrix_info_after_factor": matrix.getInfo(),
                "factor_solve_calls_at_factorization": int(
                    getattr(factor, "solve_calls", 0)
                ),
            }
            # The caller atomically saves backend facts and a read-only RSS
            # observation BEFORE runtime.sample/post gates can stop the run.
            numeric_observer(observation)
            emit("schur_factor_numeric_observed", observation)
            if type(error_code) is not int or error_code < 0:
                raise RuntimeError(f"MUMPS numeric INFOG(1)={error_code}")
        facts = {
            "label": label,
            "rows": int(matrix.getSize()[0]),
            "symbolic_raw": symbolic_raw,
            "symbolic_memory_settings": settings,
            "symbolic_memory_settings_after_memory_limit": settings_after,
            "memory_request": memory_request,
            "icntl23_readback_mb": memory_readback,
            "symbolic_seconds": symbolic_seconds,
            "numeric_seconds": numeric_seconds,
            "numeric_raw": numeric_raw,
            "matrix_info_after_factor": matrix.getInfo(),
            "numeric_resource": sample(),
        }
        backend_controls = getattr(factor, "blr_control_facts", None)
        if backend_controls is not None:
            facts["backend_control_facts"] = dict(backend_controls)
        backend_statistics = getattr(factor, "blr_statistics", None)
        if callable(backend_statistics):
            facts["backend_statistics"] = backend_statistics()
        facts["inventory_components"] = inventory(facts)
        facts["factor_solve_calls_at_factorization"] = int(
            getattr(factor, "solve_calls", 0)
        )
        if post_numeric_gate is not None:
            post_numeric_gate(facts)
        emit("schur_factor_numeric_complete", {"label": label, **facts})
        return factor, facts
    except BaseException:
        _destroy(factor)
        raise
 
 
def _matrix_values(
    matrix: Any,
    rows: np.ndarray,
    columns: np.ndarray,
) -> np.ndarray:
    if not rows.size or not columns.size:
        return np.empty((rows.size, columns.size), dtype=np.complex128)
    return np.asarray(
        matrix.getValues(rows.tolist(), columns.tolist()),
        dtype=np.complex128,
    )
 
 
def build_physical_interface_schur(
    volume: Any,
    partition: SchurPartition,
    carrier: Any,
    *,
    port_data: list[dict[str, Any]] | None = None,
    factor_factory: Callable[[Any], Any] | None = None,
    batch_columns: int = SCHUR_BATCH_COLUMNS,
    resource_sample: Callable[[], Mapping[str, Any]] | None = None,
    marker: Callable[[str, Mapping[str, Any]], None] | None = None,
    pre_numeric_gate: Callable[[Mapping[str, Any]], None] | None = None,
    post_numeric_gate: Callable[[Mapping[str, Any]], None] | None = None,
    allocation_gate: Callable[[str, Mapping[str, Any]], None] | None = None,
    owns_volume: bool = True,
    build_interface_matrix: bool = True,
) -> PhysicalInterfaceSchur:
    """Assemble sparse ``S_V`` and, when requested, ``[S_V B; -D H]``.

    Q2 keeps the augmented matrix for its exact direct comparison.  Q3 sets
    ``build_interface_matrix=False`` because its physical Gamma action uses
    ``S_V`` plus the carrier directly and must not retain a redundant global
    interface matrix.
    """
 
    from petsc4py import PETSc
    from .fullspace_v17_p3_oracle import _MumpsFactor
 
    if volume.getComm().getSize() != 1:
        raise ValueError("V14 Schur assembly is fixed to MPI1")
    if int(volume.getSize()[0]) != partition.active_rows:
        raise ValueError("active volume matrix does not match the partition")
    batch_columns = int(batch_columns)
    if batch_columns <= 0 or batch_columns > SCHUR_BATCH_COLUMNS:
        raise ValueError("Schur assembly batches must be at most 32 columns")
    factor_factory = _MumpsFactor if factor_factory is None else factor_factory
    if port_data is None:
        _support, port_data = _carrier_support(carrier, partition.storage_size)
    full_to_active = -np.ones(partition.storage_size, dtype=np.int64)
    full_to_active[partition.active_full_indices] = np.arange(
        partition.active_rows,
        dtype=np.int64,
    )
    gamma = partition.gamma_active_indices
    gamma_position = {int(value): index for index, value in enumerate(gamma)}
    adjacency = _csr_adjacency(volume)
    internal: list[InternalFactor] = []
    S_V = V_GG = interface_matrix = None
    try:
        # V_GG is a separate live sparse object.  Let the caller account for
        # its bounded CSR payload before PETSc allocates it.
        if allocation_gate is not None:
            vgg_nnz = sum(
                max(
                    1,
                    sum(
                        1
                        for column in adjacency[int(row)]
                        if int(column) in gamma_position
                    ),
                )
                for row in gamma
            )
            allocation_gate(
                "V_GG",
                {
                    "rows": partition.gamma_rows,
                    "nnz": int(vgg_nnz),
                    "matrix_payload_bytes": int(
                        _sparse_payload_bytes(vgg_nnz, partition.gamma_rows, PETSc)
                    ),
                    "workspace_bytes": 0,
                },
            )
        V_GG = _submatrix(volume, gamma)
        for block_index, indices in enumerate(partition.internal_blocks_active):
            if indices.size > MAX_INTERNAL_ROWS:
                raise ValueError(f"internal block {block_index} exceeds 2048 rows")
            block_set = set(indices.tolist())
            grows = np.asarray(
                [
                    row_index
                    for row_index, row in enumerate(gamma)
                    if block_set.intersection(adjacency[int(row)])
                ],
                dtype=np.int64,
            )
            gcols = np.asarray(
                sorted(
                    {
                        gamma_position[column]
                        for row in indices
                        for column in adjacency[int(row)]
                        if column in gamma_position
                    }
                ),
                dtype=np.int64,
            )
            if allocation_gate is not None:
                coupling_bytes = int(
                    (grows.size * indices.size + indices.size * gcols.size)
                    * np.dtype(PETSc.ScalarType).itemsize
                )
                allocation_gate(
                    f"internal_coupling_{block_index}",
                    {
                        "block_index": block_index,
                        "rows": int(indices.size),
                        "grows": int(grows.size),
                        "gcols": int(gcols.size),
                        "coupling_bytes": coupling_bytes,
                        "index_bytes": int(
                            indices.nbytes + grows.nbytes + gcols.nbytes
                        ),
                        "workspace_bytes": int(
                            (grows.size + gcols.size)
                            * np.dtype(PETSc.ScalarType).itemsize
                        ),
                    },
                )
            A_gi = _matrix_values(volume, gamma[grows], indices)
            A_i_g = _matrix_values(volume, indices, gamma[gcols])
            Aii = _submatrix(volume, indices)
            try:
                factor, factor_facts = _prepare_factor(
                    Aii,
                    factor_factory,
                    label=f"internal_{block_index}",
                    resource_sample=resource_sample,
                    marker=marker,
                    pre_numeric_gate=pre_numeric_gate,
                    post_numeric_gate=post_numeric_gate,
                    inventory_components=lambda _facts, A_gi=A_gi, A_i_g=A_i_g, indices=indices, grows=grows, gcols=gcols: {
                        "coupling_bytes": int(A_gi.nbytes + A_i_g.nbytes),
                        "index_bytes": int(indices.nbytes + grows.nbytes + gcols.nbytes),
                        "workspace_bytes": int(2 * indices.size * np.dtype(np.complex128).itemsize),
                    },
                )
            except BaseException:
                _destroy(Aii)
                raise
            item = InternalFactor(
                block_index=block_index,
                indices=indices.copy(),
                matrix=Aii,
                factor=factor,
                grows=grows,
                gcols=gcols,
                A_gi=A_gi,
                A_i_g=A_i_g,
                symbolic_raw=factor_facts["symbolic_raw"],
                numeric_raw=factor_facts["numeric_raw"],
                memory_request=factor_facts["memory_request"],
                symbolic_seconds=float(factor_facts["symbolic_seconds"]),
                numeric_seconds=float(factor_facts["numeric_seconds"]),
            )
            internal.append(item)

        # Generate a bounded Gamma-row union on demand.  Only the current row
        # is materialized; ``row_nnz`` is the small preallocation ledger used
        # for both the volume Schur and the augmented interface matrix.
        internal_columns_by_grow: dict[int, list[np.ndarray]] = {}
        for item in internal:
            for grow in item.grows:
                internal_columns_by_grow.setdefault(int(grow), []).append(item.gcols)

        def gamma_row_columns(row_index: int) -> np.ndarray:
            row = int(gamma[row_index])
            pieces: list[np.ndarray] = []
            direct = np.asarray(
                [
                    gamma_position[int(column)]
                    for column in adjacency[row]
                    if int(column) in gamma_position
                ],
                dtype=np.int64,
            )
            if direct.size:
                pieces.append(direct)
            pieces.extend(internal_columns_by_grow.get(row_index, ()))
            pieces.append(np.asarray([row_index], dtype=np.int64))
            return np.unique(np.concatenate(pieces)).astype(PETSc.IntType, copy=False)

        row_nnz = np.empty(partition.gamma_rows, dtype=PETSc.IntType)
        for row_index in range(partition.gamma_rows):
            columns = gamma_row_columns(row_index)
            row_nnz[row_index] = max(1, int(columns.size))
            del columns
        if allocation_gate is not None:
            allocation_gate(
                "S_V",
                {
                    "rows": partition.gamma_rows,
                    "nnz": int(np.sum(row_nnz, dtype=np.int64)),
                    "matrix_payload_bytes": int(
                        _sparse_payload_bytes(
                            int(np.sum(row_nnz, dtype=np.int64)),
                            partition.gamma_rows,
                            PETSc,
                        )
                    ),
                    "workspace_bytes": int(
                        max(
                            1,
                            max(
                                (
                                    (
                                        2 * item.indices.size + item.grows.size
                                    )
                                    * min(batch_columns, item.gcols.size)
                                    * np.dtype(PETSc.ScalarType).itemsize
                                    + 1 * 1024**2
                                    for item in internal
                                ),
                                default=0,
                            ),
                        )
                    ),
                },
            )
        S_V = PETSc.Mat().createAIJ(
            [partition.gamma_rows, partition.gamma_rows],
            nnz=row_nnz,
            comm=volume.getComm(),
        )
        S_V.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)
        for row_index, row in enumerate(gamma):
            base_columns = gamma_row_columns(row_index)
            if base_columns.size:
                values = _matrix_values(
                    volume,
                    np.asarray([row], dtype=PETSc.IntType),
                    gamma[base_columns],
                )[0]
                S_V.setValues(
                    [row_index],
                    base_columns.tolist(),
                    values,
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
            elif partition.gamma_rows:
                S_V.setValue(
                    row_index,
                    row_index,
                    0.0,
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
            del base_columns
        for item in internal:
            if not item.grows.size or not item.gcols.size:
                continue
            for start in range(0, item.gcols.size, batch_columns):
                stop = min(start + batch_columns, item.gcols.size)
                rhs_values = item.A_i_g[:, start:stop]
                solutions = np.column_stack(
                    [
                        _solve_array_with_factor(item, rhs_values[:, column])
                        for column in range(rhs_values.shape[1])
                    ]
                )
                contribution = item.A_gi @ solutions
                S_V.setValues(
                    item.grows.tolist(),
                    item.gcols[start:stop].tolist(),
                    -contribution,
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
        S_V.assemble()
        for item in internal:
            item.solve_calls_at_build = int(getattr(item.factor, "solve_calls", 0))
        port_maps = _compact_port_data(
            port_data,
            full_to_active,
            gamma_position,
        )
        if not build_interface_matrix:
            factor_facts = {
                "internal": [
                    {
                        "block_index": item.block_index,
                        "rows": int(item.indices.size),
                        "grows": int(item.grows.size),
                        "gcols": int(item.gcols.size),
                        "symbolic_raw": item.symbolic_raw,
                        "numeric_raw": item.numeric_raw,
                        "memory_request": item.memory_request,
                        "symbolic_seconds": item.symbolic_seconds,
                        "numeric_seconds": item.numeric_seconds,
                        "matrix_info": item.matrix.getInfo(),
                        "solve_calls_at_build": item.solve_calls_at_build,
                        "coupling_bytes": int(item.A_gi.nbytes + item.A_i_g.nbytes),
                        "index_bytes": int(
                            item.indices.nbytes + item.grows.nbytes + item.gcols.nbytes
                        ),
                    }
                    for item in internal
                ],
                "S_V": S_V.getInfo(),
                "interface": {
                    "rows": int(partition.gamma_rows + len(port_maps)),
                    "matrix_info": None,
                    "factor": None,
                    "factor_status": "NOT_BUILT_Q3_MATRIX_FREE",
                },
                "batch_columns": batch_columns,
                "interface_matrix_built": False,
            }
            return PhysicalInterfaceSchur(
                volume=volume,
                partition=partition,
                S_V=S_V,
                V_GG=V_GG,
                interface_matrix=None,
                internal=internal,
                interface_factor=None,
                port_data=port_maps,
                factor_facts=factor_facts,
                owns_volume=bool(owns_volume),
            )
        # ``row_nnz`` is the exact preallocation ledger for S_V and can be
        # reused for the augmented volume rows without a full CSR copy.
        b_port_columns: dict[int, set[int]] = {}
        for port, entry in enumerate(port_maps):
            interface_column = partition.gamma_rows + port
            for row in entry["b_gamma"]:
                b_port_columns.setdefault(int(row), set()).add(interface_column)
        interface_nnz = np.empty(
            partition.gamma_rows + len(port_maps), dtype=PETSc.IntType
        )
        for row in range(partition.gamma_rows):
            interface_nnz[row] = max(
                1, int(row_nnz[row]) + len(b_port_columns.get(row, ()))
            )
        for port, entry in enumerate(port_maps):
            d_columns = np.unique(entry["d_gamma"])
            interface_nnz[partition.gamma_rows + port] = max(
                1, int(d_columns.size) + 1
            )
        if allocation_gate is not None:
            allocation_gate(
                "interface_matrix",
                {
                    "rows": int(interface_nnz.size),
                    "nnz": int(np.sum(interface_nnz, dtype=np.int64)),
                    "matrix_payload_bytes": int(
                        _sparse_payload_bytes(
                            int(np.sum(interface_nnz, dtype=np.int64)),
                            int(interface_nnz.size),
                            PETSc,
                        )
                    ),
                    "workspace_bytes": int(interface_nnz.size * np.dtype(PETSc.ScalarType).itemsize),
                },
            )
        del row_nnz, b_port_columns
        # Keep the row helper's closure valid while releasing its large graph
        # backing objects before the augmented matrix is populated.
        internal_columns_by_grow.clear()
        adjacency.clear()
        interface_matrix = PETSc.Mat().createAIJ(
            [partition.gamma_rows + len(port_maps)] * 2,
            nnz=interface_nnz,
            comm=volume.getComm(),
        )
        interface_matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)
        for row in range(partition.gamma_rows):
            columns, values = S_V.getRow(row)
            if len(columns):
                interface_matrix.setValues(
                    [row],
                    np.asarray(columns).tolist(),
                    values,
                )
        for port, entry in enumerate(port_maps):
            interface_row = partition.gamma_rows + port
            if entry["b_gamma"].size:
                interface_matrix.setValues(
                    entry["b_gamma"].tolist(),
                    [interface_row],
                    entry["b_values"][:, None],
                )
            if entry["d_gamma"].size:
                interface_matrix.setValues(
                    [interface_row],
                    entry["d_gamma"].tolist(),
                    -entry["d_values"][None, :],
                )
            interface_matrix.setValue(
                interface_row,
                interface_row,
                entry["normalization_h"],
            )
        interface_matrix.assemble()
        factor_facts = {
            "internal": [
                {
                    "block_index": item.block_index,
                    "rows": int(item.indices.size),
                    "grows": int(item.grows.size),
                    "gcols": int(item.gcols.size),
                    "symbolic_raw": item.symbolic_raw,
                    "numeric_raw": item.numeric_raw,
                    "memory_request": item.memory_request,
                    "symbolic_seconds": item.symbolic_seconds,
                    "numeric_seconds": item.numeric_seconds,
                    "matrix_info": item.matrix.getInfo(),
                    "solve_calls_at_build": item.solve_calls_at_build,
                    "coupling_bytes": int(item.A_gi.nbytes + item.A_i_g.nbytes),
                    "index_bytes": int(
                        item.indices.nbytes + item.grows.nbytes + item.gcols.nbytes
                    ),
                }
                for item in internal
            ],
            "S_V": S_V.getInfo(),
            "interface": {
                "rows": int(interface_matrix.getSize()[0]),
                "matrix_info": interface_matrix.getInfo(),
                "factor": None,
                "factor_status": "NOT_BUILT_BY_CORE",
            },
            "batch_columns": batch_columns,
        }
        return PhysicalInterfaceSchur(
            volume=volume,
            partition=partition,
            S_V=S_V,
            V_GG=V_GG,
            interface_matrix=interface_matrix,
            internal=internal,
            interface_factor=None,
            port_data=port_maps,
            factor_facts=factor_facts,
            owns_volume=bool(owns_volume),
        )
    except BaseException:
        for item in internal:
            _destroy(item.factor)
            _destroy(item.matrix)
        for value in (interface_matrix, S_V, V_GG):
            _destroy(value)
        raise


def _solve_array_with_factor(
    item: InternalFactor,
    values: np.ndarray,
) -> np.ndarray:
    rhs = item.matrix.createVecRight()
    solution = item.matrix.createVecRight()
    try:
        rhs.array[:] = values
        item.factor.solve_repeated(rhs, solution)
        return np.asarray(solution.array).copy()
    finally:
        rhs.destroy()
        solution.destroy()


def factorize_interface_schur(
    core: PhysicalInterfaceSchur,
    *,
    factor_factory: Callable[[Any], Any] | None = None,
    resource_sample: Callable[[], Mapping[str, Any]] | None = None,
    marker: Callable[[str, Mapping[str, Any]], None] | None = None,
    pre_numeric_gate: Callable[[Mapping[str, Any]], None] | None = None,
    post_numeric_gate: Callable[[Mapping[str, Any]], None] | None = None,
    inventory_components: Mapping[str, int]
    | Callable[[Mapping[str, Any]], Mapping[str, int]]
    | None = None,
) -> dict[str, Any]:
    """Optionally attach the global interface factor to an assembled core.

    Keeping this operation separate is intentional: a resource-controlled
    global numeric phase must not invalidate the already checked local
    elimination, sparse Schur action, adjoint and recovery paths.
    """

    if core.destroyed:
        raise RuntimeError("cannot factorize a destroyed Schur core")
    if core.interface_factor is not None:
        raise RuntimeError("the global interface factor is already attached")
    from .fullspace_v17_p3_oracle import _MumpsFactor

    factor_factory = _MumpsFactor if factor_factory is None else factor_factory
    factor, facts = _prepare_factor(
        core.interface_matrix,
        factor_factory,
        label="interface",
        resource_sample=resource_sample,
        marker=marker,
        pre_numeric_gate=pre_numeric_gate,
        post_numeric_gate=post_numeric_gate,
        inventory_components=inventory_components,
    )
    core.interface_factor = factor
    core.factor_facts["interface"]["factor"] = facts
    core.factor_facts["interface"]["factor_status"] = "NUMERIC_READY"
    return facts


def _compact_port_data(
    port_data: Iterable[Mapping[str, Any]],
    full_to_active: np.ndarray,
    gamma_position: Mapping[int, int],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entry in port_data:
        b_rows = np.asarray(entry["coupling_rows"], dtype=np.int64)
        b_values = np.asarray(entry["coupling_values"], dtype=np.complex128)
        d_rows = np.asarray(entry["projection_rows"], dtype=np.int64)
        d_values = np.asarray(entry["projection_values"], dtype=np.complex128)
        b_keep = _nonzero_rows(b_values)
        d_keep = _nonzero_rows(d_values)
        b_active = full_to_active[b_rows[b_keep]]
        d_active = full_to_active[d_rows[d_keep]]
        if np.any(b_active < 0) or np.any(d_active < 0):
            raise ValueError("port support contains an inactive row")
        b_gamma = np.asarray(
            [gamma_position[int(value)] for value in b_active],
            dtype=np.int64,
        )
        d_gamma = np.asarray(
            [gamma_position[int(value)] for value in d_active],
            dtype=np.int64,
        )
        result.append(
            {
                "port": int(entry["port"]),
                "b_gamma": b_gamma,
                "b_values": b_values[b_keep],
                "b_full": b_rows[b_keep],
                "d_gamma": d_gamma,
                "d_values": d_values[d_keep],
                "d_full": d_rows[d_keep],
                "normalization_h": complex(entry["normalization_h"]),
            }
        )
    return result


__all__ = [
    "InterfaceFintAdapter",
    "InterfaceLocalSmoother",
    "InterfacePatchFactor",
    "InternalFactor",
    "InterfaceCoarsePair",
    "MAX_INTERFACE_ROWS",
    "MAX_INTERFACE_WORKSPACE_BYTES",
    "MAX_INTERNAL_ROWS",
    "PairedInterfaceBasis",
    "PairedPatchBasis",
    "PhysicalInterfaceSchur",
    "SCHUR_PROFILE",
    "SCHUR_SCHEMA",
    "SchurPartition",
    "apply_interface_cycle",
    "build_interface_local_smoother",
    "build_interface_candidate_directions",
    "build_port_direction_families",
    "build_interface_coarse_pair",
    "build_interface_partition",
    "build_paired_patch_basis",
    "build_physical_interface_schur",
    "factorize_interface_schur",
    "interface_patch_rows_from_core",
    "orthonormalize_paired_directions",
    "v11_memory_request_mb",
]

 
 
 
 
