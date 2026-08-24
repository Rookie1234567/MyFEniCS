"""Pure NumPy coupled lower/upper interface algebra for Task040 V3.

This module only combines the reviewed small projected matrices and a pure
full-side mechanism algebra.  It does not assemble a FEM operator, construct
a PETSc/MUMPS factor, or load an interface packet.  The full 776-dimensional
result is a packet-dependent mechanism oracle; callers that need a scalable
candidate must apply the later bounded-rank contract.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

EXPECTED_GROUP_ORDER = ("group0", "group1", "group2")
EXPECTED_SPAN_SIZES = (296, 776, 480)
CONDITION_LIMIT = 1.0e12

__all__ = [
    "CONDITION_LIMIT",
    "EXPECTED_GROUP_ORDER",
    "EXPECTED_SPAN_SIZES",
    "assemble_coupled_interface_matrices",
    "assemble_augmented_coupled_interface_matrices",
    "CoupledInterfacePetrovAction",
    "CoupledFullSidePetrovAction",
    "matrix_diagnostics",
    "solve_coupled_interface",
]


def _matrix_sha256(matrix: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(matrix).tobytes()).hexdigest()


def _as_matrix(value: Any, name: str, expected_shape: tuple[int, int]) -> np.ndarray:
    matrix = np.asarray(value)
    if matrix.dtype != np.dtype(np.complex128):
        raise ValueError(f"{name} must have complex128 dtype")
    if matrix.shape != expected_shape or matrix.ndim != 2:
        raise ValueError(f"{name} must have shape {expected_shape}")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{name} is nonfinite")
    return matrix


def matrix_diagnostics(
    matrix: np.ndarray,
    *,
    expected_shape: tuple[int, int] | None = None,
    square: bool = True,
) -> dict[str, Any]:
    """Return finite/rank/SVD/hash diagnostics for a small matrix.

    ``condition`` is reported only for square matrices.  Rectangular
    cross-interface blocks still receive their finite/rank/SVD/hash audit,
    but no square-system condition number is implied.
    """

    value = np.asarray(matrix)
    if value.dtype != np.dtype(np.complex128) or value.ndim != 2:
        raise ValueError("diagnostic matrix must be a complex128 2D array")
    if expected_shape is not None and value.shape != expected_shape:
        raise ValueError(f"diagnostic matrix shape {value.shape} != {expected_shape}")
    if square and value.shape[0] != value.shape[1]:
        raise ValueError("diagnostic matrix must be square")
    if not np.isfinite(value).all():
        raise ValueError("diagnostic matrix must be finite")
    singular_values = np.linalg.svd(value, compute_uv=False)
    rank = int(np.linalg.matrix_rank(value))
    condition = None
    if square:
        condition = (
            float(singular_values[0] / singular_values[-1])
            if singular_values.size and singular_values[-1] > 0.0
            else float("inf")
        )
    return {
        "shape": [int(item) for item in value.shape],
        "dtype": "complex128",
        "rank": rank,
        "singular_values": [float(item) for item in singular_values],
        "condition": condition,
        "sha256": _matrix_sha256(value),
    }


def _block_diagonal(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    result = np.zeros(
        (left.shape[0] + right.shape[0], left.shape[1] + right.shape[1]),
        dtype=np.complex128,
    )
    result[: left.shape[0], : left.shape[1]] = left
    result[left.shape[0] :, left.shape[1] :] = right
    return result


def _block_diagnostics(
    matrix: np.ndarray, lower_span: int, upper_span: int
) -> dict[str, dict[str, Any]]:
    slices = {
        "LL": (slice(0, lower_span), slice(0, lower_span)),
        "LU": (slice(0, lower_span), slice(lower_span, lower_span + upper_span)),
        "UL": (slice(lower_span, lower_span + upper_span), slice(0, lower_span)),
        "UU": (
            slice(lower_span, lower_span + upper_span),
            slice(lower_span, lower_span + upper_span),
        ),
    }
    full_norm = float(np.linalg.norm(matrix, ord="fro"))
    scale = max(full_norm, np.finfo(float).tiny)
    result: dict[str, dict[str, Any]] = {}
    for name, (row_slice, col_slice) in slices.items():
        block = np.asarray(matrix[row_slice, col_slice], dtype=np.complex128)
        result[name] = {
            **matrix_diagnostics(block, square=False),
            "frobenius_norm": float(np.linalg.norm(block, ord="fro")),
            "relative_frobenius_norm": float(np.linalg.norm(block, ord="fro") / scale),
        }
    return result


def assemble_coupled_interface_matrices(
    group_matrices: Sequence[Mapping[str, np.ndarray]],
    *,
    expected_span_sizes: tuple[int, int, int] = EXPECTED_SPAN_SIZES,
) -> dict[str, Any]:
    """Assemble the scalar/exact joint lower-plus-upper projected matrices.

    ``group_matrices`` is ordered group0, group1, group2.  Each mapping has
    ``gram``, ``projected_scalar`` and ``projected_exact`` arrays.  The middle
    group is always interpreted as lower rows/columns followed by upper rows.
    """

    if len(group_matrices) != 3:
        raise ValueError("coupled interface algebra requires exactly three groups")
    if len(expected_span_sizes) != 3:
        raise ValueError("three expected group spans are required")
    lower_span, middle_span, upper_span = (int(item) for item in expected_span_sizes)
    if middle_span != lower_span + upper_span:
        raise ValueError("middle span must equal lower plus upper span")

    required = ("gram", "projected_scalar", "projected_exact")
    groups: list[dict[str, np.ndarray]] = []
    group_diagnostics: list[dict[str, Any]] = []
    for group_index, payload in enumerate(group_matrices):
        expected_shape = (int(expected_span_sizes[group_index]),) * 2
        if any(name not in payload for name in required):
            raise ValueError(
                f"group{group_index} projected matrix inventory is incomplete"
            )
        matrices = {
            name: _as_matrix(
                payload[name], f"group{group_index}.{name}", expected_shape
            )
            for name in required
        }
        groups.append(matrices)
        group_diagnostics.append(
            {
                "group": f"group{group_index}",
                **{
                    name: matrix_diagnostics(matrix, expected_shape=expected_shape)
                    for name, matrix in matrices.items()
                },
            }
        )

    joint_names = ("projected_scalar", "projected_exact")
    joint = {
        name: groups[1][name] + _block_diagonal(groups[0][name], groups[2][name])
        for name in joint_names
    }
    joint_diagnostics = {
        name: matrix_diagnostics(matrix, expected_shape=(middle_span, middle_span))
        for name, matrix in joint.items()
    }
    return {
        "group_order": list(EXPECTED_GROUP_ORDER),
        "span_sizes": [lower_span, middle_span, upper_span],
        "lower_span": lower_span,
        "upper_span": upper_span,
        "joint_projected_scalar": joint["projected_scalar"],
        "joint_projected_exact": joint["projected_exact"],
        "diagnostics": {
            "groups": group_diagnostics,
            "joint": joint_diagnostics,
            "joint_exact_blocks": _block_diagnostics(
                joint["projected_exact"], lower_span, upper_span
            ),
            "joint_scalar_blocks": _block_diagnostics(
                joint["projected_scalar"], lower_span, upper_span
            ),
            "condition_limit": CONDITION_LIMIT,
        },
    }


def assemble_augmented_coupled_interface_matrices(
    group_matrices: Sequence[Mapping[str, np.ndarray]],
    projected_middle_group_schur: np.ndarray,
    *,
    expected_span_sizes: tuple[int, int, int] = EXPECTED_SPAN_SIZES,
) -> dict[str, Any]:
    """Assemble the V3 true joint operator from the augmented packet.

    The legacy ``group1.projected_exact`` is the incoming block-diagonal
    ``E0+E2`` contribution.  The augmented matrix is the separately
    projected middle-group Schur ``E1`` plus that legacy contribution.  The
    old group0/group2 directed-neighbor matrices are retained in the result
    only as diagnostics; they are not silently renamed into local Schurs.
    """

    legacy = assemble_coupled_interface_matrices(
        group_matrices, expected_span_sizes=expected_span_sizes
    )
    lower_span, middle_span, upper_span = (int(item) for item in expected_span_sizes)
    middle = _as_matrix(
        projected_middle_group_schur,
        "projected_middle_group_schur",
        (middle_span, middle_span),
    )
    outer_block_diagonal = _as_matrix(
        group_matrices[1]["projected_exact"],
        "group1.projected_exact",
        (middle_span, middle_span),
    )
    joint_exact = middle + outer_block_diagonal
    joint_diagnostics = matrix_diagnostics(
        joint_exact, expected_shape=(middle_span, middle_span)
    )
    diagnostics = legacy["diagnostics"]
    diagnostics["augmented"] = True
    diagnostics["joint_exact_definition"] = (
        "projected_middle_group_schur + projected_exact_group1"
    )
    diagnostics["middle_group_schur"] = matrix_diagnostics(
        middle, expected_shape=(middle_span, middle_span)
    )
    diagnostics["joint_exact"] = joint_diagnostics
    diagnostics["joint_exact_condition_gate"] = (
        joint_diagnostics["condition"] is not None
        and joint_diagnostics["condition"] <= CONDITION_LIMIT
    )
    diagnostics["joint_exact_blocks"] = _block_diagnostics(
        joint_exact, lower_span, upper_span
    )
    return {
        **legacy,
        "joint_projected_exact": joint_exact,
        "projected_middle_group_schur": middle,
        "diagnostics": diagnostics,
    }


def _svd_factorization(
    operator: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, float]:
    value = np.asarray(operator)
    if value.dtype != np.dtype(np.complex128) or value.ndim != 2:
        raise ValueError("coupled operator must be a complex128 matrix")
    if value.shape[0] != value.shape[1] or not np.isfinite(value).all():
        raise ValueError("coupled operator must be finite and square")
    u, singular_values, vh = np.linalg.svd(value, full_matrices=False)
    if singular_values.size == 0 or not np.isfinite(singular_values).all():
        raise ValueError("coupled operator has no finite singular values")
    tolerance = np.finfo(float).eps * max(value.shape) * singular_values[0]
    rank = int(np.count_nonzero(singular_values > tolerance))
    if rank != value.shape[0]:
        raise ValueError("coupled projected operator is numerically singular")
    condition = float(singular_values[0] / singular_values[-1])
    return u, singular_values, vh, rank, condition


def _svd_apply(
    factors: tuple[np.ndarray, np.ndarray, np.ndarray, int, float],
    rhs: np.ndarray,
) -> np.ndarray:
    u, singular_values, vh, _rank, _condition = factors
    projected = u.conj().T @ rhs
    if rhs.ndim == 1:
        return vh.conj().T @ (projected / singular_values)
    return vh.conj().T @ (projected / singular_values[:, None])


class CoupledInterfacePetrovAction:
    """Apply one distributed owner-local correction through ``E_joint``.

    This is the Gamma-only distributed subcomponent, not the V3-2 full-side
    action below.

    ``z_local`` and ``y_local`` are only the current rank's Gamma rows.  The
    sole collective is the small Petrov contraction ``Y^H rhs``; no FE-sized
    numeric array or full basis is gathered.  ``Y`` is intentionally accepted
    separately from ``Z`` so non-Hermitian, non-unit Gram fixtures remain
    explicit.
    """

    def __init__(
        self,
        joint_matrix: np.ndarray,
        z_local: np.ndarray,
        y_local: np.ndarray,
        *,
        comm: Any | None = None,
    ) -> None:
        self._joint = np.asarray(joint_matrix)
        self._z_local = np.asarray(z_local)
        self._y_local = np.asarray(y_local)
        self._comm = comm
        if self._joint.dtype != np.dtype(np.complex128):
            raise ValueError("joint matrix must be complex128")
        if (
            self._z_local.dtype != np.dtype(np.complex128)
            or self._y_local.dtype != np.dtype(np.complex128)
            or self._z_local.ndim != 2
            or self._y_local.shape != self._z_local.shape
            or self._z_local.shape[1] != self._joint.shape[0]
        ):
            raise ValueError("owner-local Z/Y and joint matrix shapes do not match")
        if (
            not np.isfinite(self._joint).all()
            or not np.isfinite(self._z_local).all()
            or not np.isfinite(self._y_local).all()
        ):
            raise ValueError("coupled Petrov inputs must be finite")
        self._svd = _svd_factorization(self._joint)
        _u, singular_values, _vh, rank, condition = self._svd
        self._joint_shape = tuple(int(item) for item in self._joint.shape)
        self._joint_rank = int(rank)
        self._joint_condition = float(condition)
        self._singular_value_summary = tuple(float(item) for item in singular_values)
        self._apply_count = 0
        self._destroyed = False

    def _collect_small(self, local: np.ndarray) -> np.ndarray:
        if self._comm is None or int(self._comm.Get_size()) == 1:
            return local
        result = np.empty_like(local)
        self._comm.Allreduce(local, result)
        return result

    def apply(self, rhs_local: np.ndarray) -> np.ndarray:
        """Return ``Z_local E_joint^{-1} Y^H rhs`` for local rows."""

        if self._destroyed:
            raise RuntimeError("coupled Petrov action is destroyed")
        rhs = np.asarray(rhs_local, dtype=np.complex128)
        if rhs.ndim not in (1, 2) or rhs.shape[0] != self._z_local.shape[0]:
            raise ValueError("owner-local RHS has the wrong shape")
        if not np.isfinite(rhs).all():
            raise ValueError("owner-local RHS is nonfinite")
        local_projection = self._y_local.conj().T @ rhs
        global_projection = self._collect_small(local_projection)
        coefficients = _svd_apply(self._svd, global_projection)
        result = self._z_local @ coefficients
        self._apply_count += 1
        return result

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "joint_shape": list(self._joint_shape),
            "joint_rank": self._joint_rank,
            "joint_condition": self._joint_condition,
            "singular_values": list(self._singular_value_summary),
            "apply_count": self._apply_count,
            "owner_local_rows": int(self._z_local.shape[0])
            if not self._destroyed
            else None,
            "owner_local_basis_contract": True,
            "basis_replication_verified": False,
            "fe_numeric_allgather": False,
            "dense_factor_retained": self._svd is not None,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        self._joint = None
        self._z_local = None
        self._y_local = None
        self._comm = None
        self._svd = None
        self._destroyed = True


class CoupledFullSidePetrovAction:
    """Apply the packet-dependent full-side coupled correction.

    This pure callback carrier is a tiny algebra oracle.  A formal PETSc
    consumer must provide owner-local restriction, synthesis, and factor
    back-substitution without converting FE vectors into global NumPy arrays.

    The mechanism uses the explicit block-elimination identity

    ``A = [[E, C], [D, B]]`` and ``S = E - C B^-1 D``.  For a full-side
    residual ``r = (r_Gamma, r_I)``, the three group factors provide the
    block-diagonal ``B^-1`` in both places below::

        x_base = (0, B^-1 r_I)
        q      = r - A x_base
        rhs    = Y_Gamma^H R_Gamma q
        c      = (Y_Gamma^H S Z_Gamma)^-1 rhs
        gamma  = Z_Gamma c
        dx     = (gamma, -B^-1 D gamma)
        x      = x_base + dx

    ``base_solve`` is the local/group pre-correction, ``interface_restrict``
    performs the owner-local Gamma restriction, ``z_synthesize`` is the
    explicit Z synthesis, and ``harmonic_back_sub`` must use the same three
    group-factor solves to produce the full-side correction.  The callbacks
    are deliberately narrow so this pure core cannot silently construct an
    exact-interface oracle or replace the three allowed factors with a sweep.
    Only the ``Y_Gamma^H`` contraction is reduced across ``comm``; no
    FE-sized numeric array is gathered.
    """

    def __init__(
        self,
        joint_matrix: np.ndarray,
        y_local: np.ndarray,
        *,
        full_size: int,
        base_solve: Callable[[np.ndarray], np.ndarray],
        bare_apply: Callable[[np.ndarray], np.ndarray],
        interface_restrict: Callable[[np.ndarray], np.ndarray],
        z_synthesize: Callable[[np.ndarray], np.ndarray],
        harmonic_back_sub: Callable[[np.ndarray], np.ndarray],
        comm: Any | None = None,
        group_factor_count: int = 3,
    ) -> None:
        self._joint = np.asarray(joint_matrix)
        self._y_local = np.asarray(y_local)
        self._full_size = int(full_size)
        self._base_solve = base_solve
        self._bare_apply = bare_apply
        self._interface_restrict = interface_restrict
        self._z_synthesize = z_synthesize
        self._harmonic_back_sub = harmonic_back_sub
        self._comm = comm
        self._group_factor_count = int(group_factor_count)
        if self._joint.dtype != np.dtype(np.complex128):
            raise ValueError("full-side joint matrix must be complex128")
        if self._joint.ndim != 2 or self._joint.shape[0] != self._joint.shape[1]:
            raise ValueError("full-side joint matrix must be square")
        if self._y_local.dtype != np.dtype(np.complex128) or self._y_local.ndim != 2:
            raise ValueError("full-side local Y must be a complex128 matrix")
        if self._y_local.shape[1] != self._joint.shape[0]:
            raise ValueError("full-side local Y and joint matrix shapes do not match")
        if self._full_size <= 0 or self._group_factor_count != 3:
            raise ValueError("full-side action requires three group factors")
        if not all(
            callable(callback)
            for callback in (
                base_solve,
                bare_apply,
                interface_restrict,
                z_synthesize,
                harmonic_back_sub,
            )
        ):
            raise TypeError("full-side action callbacks must be callable")
        self._svd = _svd_factorization(self._joint)
        _u, singular_values, _vh, rank, condition = self._svd
        self._joint_shape = tuple(int(item) for item in self._joint.shape)
        self._joint_rank = int(rank)
        self._joint_condition = float(condition)
        self._singular_value_summary = tuple(float(item) for item in singular_values)
        self._apply_count = 0
        self._destroyed = False

    def _collect_small(self, local: np.ndarray) -> np.ndarray:
        if self._comm is None or int(self._comm.Get_size()) == 1:
            return local
        result = np.empty_like(local)
        self._comm.Allreduce(local, result)
        return result

    @staticmethod
    def _checked_vector(value: Any, name: str, size: int) -> np.ndarray:
        vector = np.asarray(value, dtype=np.complex128)
        if vector.ndim != 1 or vector.shape[0] != size:
            raise ValueError(f"{name} has the wrong full-side shape")
        if not np.isfinite(vector).all():
            raise ValueError(f"{name} is nonfinite")
        return vector

    def apply(self, rhs: np.ndarray) -> np.ndarray:
        """Return one full-side PC action, including harmonic back-substitution."""

        if self._destroyed:
            raise RuntimeError("full-side coupled action is destroyed")
        source = self._checked_vector(rhs, "full-side RHS", self._full_size)
        base = self._checked_vector(
            self._base_solve(source), "base pre-correction", self._full_size
        )
        residual = source - self._checked_vector(
            self._bare_apply(base), "bare-F base action", self._full_size
        )
        restricted = np.asarray(self._interface_restrict(residual), dtype=np.complex128)
        if restricted.ndim != 1 or restricted.shape[0] != self._y_local.shape[0]:
            raise ValueError("interface restriction has the wrong owner-local shape")
        if not np.isfinite(restricted).all():
            raise ValueError("interface restriction is nonfinite")
        rhs_small = self._collect_small(self._y_local.conj().T @ restricted)
        coefficients = _svd_apply(self._svd, rhs_small)
        gamma = self._checked_vector(
            self._z_synthesize(coefficients),
            "Z Gamma synthesis",
            self._y_local.shape[0],
        )
        correction = self._checked_vector(
            self._harmonic_back_sub(gamma),
            "harmonic full-side back-substitution",
            self._full_size,
        )
        result = base + correction
        self._apply_count += 1
        return result

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "schema": "task040.v3_2.full_side_coupled_action.v1",
            "packet_dependent": True,
            "joint_shape": list(self._joint_shape),
            "joint_rank": self._joint_rank,
            "joint_condition": self._joint_condition,
            "singular_values": list(self._singular_value_summary),
            "cross_section_group_factor_count": self._group_factor_count,
            "exact_interface_schur_oracle_object_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "reduced_dense_factor_count": 1,
            "nested_ksp_count": 0,
            "normal_equations": False,
            "owner_local_basis_contract": True,
            "basis_replication_verified": False,
            "fe_numeric_allgather": False,
            "dense_factor_retained": self._svd is not None,
            "apply_count": self._apply_count,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._joint = None
        self._y_local = None
        self._base_solve = None
        self._bare_apply = None
        self._interface_restrict = None
        self._z_synthesize = None
        self._harmonic_back_sub = None
        self._comm = None
        self._svd = None
        self._destroyed = True


def solve_coupled_interface(matrix: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    """Solve a small non-Hermitian projected system with an SVD solve."""

    operator = np.asarray(matrix)
    vector = np.asarray(rhs, dtype=np.complex128)
    if operator.dtype != np.dtype(np.complex128) or operator.ndim != 2:
        raise ValueError("coupled operator must be a complex128 matrix")
    if operator.shape[0] != operator.shape[1] or vector.shape[0] != operator.shape[0]:
        raise ValueError("coupled operator and RHS shapes do not match")
    if not np.isfinite(operator).all() or not np.isfinite(vector).all():
        raise ValueError("coupled solve input is nonfinite")
    u, singular_values, vh = np.linalg.svd(operator, full_matrices=False)
    if singular_values.size == 0 or not np.isfinite(singular_values).all():
        raise ValueError("coupled operator has no finite singular values")
    tolerance = np.finfo(float).eps * max(operator.shape) * singular_values[0]
    if singular_values[-1] <= tolerance:
        raise ValueError("coupled projected operator is numerically singular")
    projected = u.conj().T @ vector
    if vector.ndim == 1:
        return vh.conj().T @ (projected / singular_values)
    return vh.conj().T @ (projected / singular_values[:, None])
