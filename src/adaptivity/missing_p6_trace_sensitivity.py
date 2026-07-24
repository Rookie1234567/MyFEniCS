"""Fail-closed missing-p6-trace residual diagnostics for Task035b.

The accepted fixed-trace space contains the complete p6 cell-interior space
but only a p5 edge/face trace.  This module supplies two deliberately separate
building blocks:

* an entity-local direct complement of the p5 trace in the standard p6 trace;
* exact primal and Hermitian-adjoint residuals in an already assembled
  missing-trace block.

The residual pairing exposed here is *not* a DWR estimator.  No complement
problem is solved, so the raw coordinate-wise product has neither the inverse
operator scaling nor the enriched correction required by DWR.  It may be used
to decide whether implementing a true selective-trace candidate is warranted,
but it cannot authorize such a candidate by itself.

No candidate matrix is built in this module.  In particular, a caller cannot
obtain a max-p matrix with inactive rows from this API.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

import basix
import basix.ufl
from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from .hcurl_regionwise_p import create_reduced_trace_hcurl_element


REVIEW_V1_MISSING_TRACE_GOAL_LABELS = (
    "R_m-2_n0_s_power",
    "R_m-4_n0_s_power",
    "R_m-5_n0_s_power",
    "T_m-2_n0_s_power",
    "T_m-4_n0_s_power",
    "T_m-5_n0_s_power",
    "R_m-4_n0_s_amplitude_real",
    "R_m-4_n0_s_amplitude_imag",
    "R_m-5_n0_s_amplitude_real",
    "R_m-5_n0_s_amplitude_imag",
    "T_m-2_n0_s_amplitude_real",
    "T_m-2_n0_s_amplitude_imag",
    "T_m-4_n0_s_amplitude_real",
    "T_m-4_n0_s_amplitude_imag",
    "T_m-5_n0_s_amplitude_real",
    "T_m-5_n0_s_amplitude_imag",
)


def _canonicalize_columns(values: np.ndarray) -> np.ndarray:
    """Fix the otherwise arbitrary signs of a real orthonormal basis."""

    result = np.asarray(values, dtype=np.float64).copy()
    for column in range(result.shape[1]):
        vector = result[:, column]
        pivot = int(np.argmax(np.abs(vector)))
        if vector[pivot] < 0.0:
            result[:, column] *= -1.0
    return result


def _array_sha256(values: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(values)
    payload = (
        str(contiguous.dtype).encode("ascii")
        + np.asarray(contiguous.shape, dtype=np.int64).tobytes()
        + contiguous.tobytes()
    )
    return hashlib.sha256(payload).hexdigest()


def _flatten_entity_dofs(element, dimension: int) -> np.ndarray:
    return np.asarray(
        [
            int(dof)
            for entity in element.entity_dofs[int(dimension)]
            for dof in entity
        ],
        dtype=np.int32,
    )


@dataclass(frozen=True)
class MissingTraceEntityBlock:
    """One reference edge/face complement block."""

    entity_dimension: int
    local_entity_index: int
    enriched_entity_dofs: np.ndarray
    retained_entity_dofs: np.ndarray
    missing_column_start: int
    missing_column_stop: int
    retained_embedding: np.ndarray
    missing_embedding: np.ndarray
    induced_transformations: tuple[np.ndarray, ...]

    @property
    def missing_dimension(self) -> int:
        return int(self.missing_column_stop - self.missing_column_start)


@dataclass(frozen=True)
class MissingP6TraceComplement:
    """Entity-local direct-sum coordinates for fixed p5 trace plus p6 trace."""

    trace_degree: int
    enriched_degree: int
    retained_dimension: int
    enriched_dimension: int
    missing_dimension: int
    retained_to_enriched: np.ndarray
    missing_to_enriched: np.ndarray
    entity_blocks: tuple[MissingTraceEntityBlock, ...]
    audit: Mapping[str, Any]


@dataclass(frozen=True)
class MissingTraceEntityRieszBlock:
    """Reference-entity tangential-L2 Riesz metric for one trace block.

    ``gram`` acts on primal trace coefficients.  Residual and goal-gradient
    vectors are dual covectors, so ``dual_inverse_sqrt`` is the whitening map
    used for invariant residual norms and pairings.
    """

    entity_dimension: int
    local_entity_index: int
    missing_column_start: int
    missing_column_stop: int
    gram: np.ndarray
    sqrt: np.ndarray
    dual_inverse_sqrt: np.ndarray
    eigenvalues: np.ndarray
    quadrature_degree: int
    audit: Mapping[str, Any]

    @property
    def missing_dimension(self) -> int:
        return int(self.missing_column_stop - self.missing_column_start)


@dataclass(frozen=True)
class MissingP6TraceRieszMetric:
    """Entity-direct-sum reference-cell metric for missing trace modes."""

    trace_degree: int
    enriched_degree: int
    missing_dimension: int
    block_diagonal_gram: np.ndarray
    entity_blocks: tuple[MissingTraceEntityRieszBlock, ...]
    audit: Mapping[str, Any]


@dataclass(frozen=True)
class WhitenedTraceDualCovectors:
    """Basis-invariant algebra exposed to future SVD/QR analysis."""

    whitened_covectors: np.ndarray
    dual_goal_gram: np.ndarray
    singular_values: np.ndarray
    audit: Mapping[str, Any]


def build_missing_p6_trace_complement(
    *,
    trace_degree: int = 5,
    enriched_degree: int = 6,
    tolerance: float = 2.0e-11,
) -> MissingP6TraceComplement:
    """Build an orientation-closed entity complement without a global matrix.

    The retained element is the production-independent custom element with
    p5 trace and p6 cell interior.  Its interpolation into standard p6 is
    completed entity by entity:

    * one missing mode on every edge;
    * twenty missing modes on every face.

    The complement is a direct complement, not a global Euclidean orthogonal
    complement.  Entity locality is retained so that a later implementation
    can give selected shared entities physical global numbers.
    """

    trace_degree = int(trace_degree)
    enriched_degree = int(enriched_degree)
    tolerance = float(tolerance)
    if (trace_degree, enriched_degree) != (5, 6):
        raise ValueError(
            "Task035b missing-trace authority is currently fixed to p5/p6"
        )
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("complement tolerance must be positive and finite")

    retained = create_reduced_trace_hcurl_element(
        trace_degree,
        enriched_degree,
    ).element
    enriched = basix.ufl.element(
        "N1curl",
        "hexahedron",
        enriched_degree,
    ).basix_element
    retained_to_enriched = np.asarray(
        basix.compute_interpolation_operator(retained, enriched),
        dtype=np.float64,
    )
    if retained_to_enriched.shape != (
        int(enriched.dim),
        int(retained.dim),
    ):
        raise RuntimeError("p5-trace to p6 interpolation has the wrong shape")
    retained_rank = int(np.linalg.matrix_rank(retained_to_enriched))
    if retained_rank != int(retained.dim):
        raise RuntimeError("p5-trace/p6-interior embedding is rank deficient")

    blocks: list[MissingTraceEntityBlock] = []
    missing_columns: list[np.ndarray] = []
    missing_offset = 0
    maximum_equivariance_error = 0.0
    maximum_complement_invariance_error = 0.0
    maximum_induced_unitarity_error = 0.0
    entity_missing_dimensions: dict[str, list[int]] = {
        "edge": [],
        "face": [],
    }
    transformation_key = {1: "interval", 2: "quadrilateral"}
    label_by_dimension = {1: "edge", 2: "face"}

    for dimension in (1, 2):
        high_transformations = np.asarray(
            enriched.entity_transformations()[
                transformation_key[dimension]
            ],
            dtype=np.float64,
        )
        low_transformations = np.asarray(
            retained.entity_transformations()[
                transformation_key[dimension]
            ],
            dtype=np.float64,
        )
        if len(high_transformations) != len(low_transformations):
            raise RuntimeError(
                "retained and enriched entity transformations disagree"
            )
        for entity_index, (high_rows_raw, low_rows_raw) in enumerate(
            zip(
                enriched.entity_dofs[dimension],
                retained.entity_dofs[dimension],
                strict=True,
            )
        ):
            high_rows = np.asarray(high_rows_raw, dtype=np.int32)
            low_rows = np.asarray(low_rows_raw, dtype=np.int32)
            retained_block = retained_to_enriched[
                np.ix_(high_rows, low_rows)
            ]
            block_rank = int(np.linalg.matrix_rank(retained_block))
            if block_rank != len(low_rows):
                raise RuntimeError(
                    "retained trace embedding is rank deficient on "
                    f"entity ({dimension}, {entity_index})"
                )
            orthogonal, _upper = np.linalg.qr(
                retained_block,
                mode="complete",
            )
            missing_block = _canonicalize_columns(
                orthogonal[:, len(low_rows) :]
            )
            missing_count = int(missing_block.shape[1])
            if missing_count <= 0:
                raise RuntimeError("trace entity has no missing enriched mode")
            full_column = np.zeros(
                (int(enriched.dim), missing_count),
                dtype=np.float64,
            )
            full_column[high_rows, :] = missing_block
            missing_columns.append(full_column)

            projector = missing_block @ missing_block.T
            induced: list[np.ndarray] = []
            for high_transform, low_transform in zip(
                high_transformations,
                low_transformations,
                strict=True,
            ):
                equivariance_error = float(
                    np.max(
                        np.abs(
                            high_transform @ retained_block
                            - retained_block @ low_transform
                        ),
                        initial=0.0,
                    )
                )
                invariance_error = float(
                    np.max(
                        np.abs(
                            (
                                np.eye(len(high_rows), dtype=np.float64)
                                - projector
                            )
                            @ high_transform
                            @ missing_block
                        ),
                        initial=0.0,
                    )
                )
                induced_transform = (
                    missing_block.T @ high_transform @ missing_block
                )
                unitarity_error = float(
                    np.max(
                        np.abs(
                            induced_transform.T @ induced_transform
                            - np.eye(missing_count, dtype=np.float64)
                        ),
                        initial=0.0,
                    )
                )
                maximum_equivariance_error = max(
                    maximum_equivariance_error,
                    equivariance_error,
                )
                maximum_complement_invariance_error = max(
                    maximum_complement_invariance_error,
                    invariance_error,
                )
                maximum_induced_unitarity_error = max(
                    maximum_induced_unitarity_error,
                    unitarity_error,
                )
                induced.append(induced_transform)

            blocks.append(
                MissingTraceEntityBlock(
                    entity_dimension=dimension,
                    local_entity_index=entity_index,
                    enriched_entity_dofs=high_rows.copy(),
                    retained_entity_dofs=low_rows.copy(),
                    missing_column_start=missing_offset,
                    missing_column_stop=missing_offset + missing_count,
                    retained_embedding=retained_block.copy(),
                    missing_embedding=missing_block.copy(),
                    induced_transformations=tuple(induced),
                )
            )
            missing_offset += missing_count
            entity_missing_dimensions[
                label_by_dimension[dimension]
            ].append(missing_count)

    missing_to_enriched = np.concatenate(missing_columns, axis=1)
    interior_rows = _flatten_entity_dofs(enriched, 3)
    interior_leakage = float(
        np.max(
            np.abs(missing_to_enriched[interior_rows, :]),
            initial=0.0,
        )
    )
    full_change_of_coordinates = np.concatenate(
        (retained_to_enriched, missing_to_enriched),
        axis=1,
    )
    full_rank = int(np.linalg.matrix_rank(full_change_of_coordinates))
    full_condition_number = float(
        np.linalg.cond(full_change_of_coordinates)
    )
    expected_missing = int(enriched.dim - retained.dim)
    checks = {
        "retained_embedding_full_column_rank": (
            retained_rank == int(retained.dim)
        ),
        "missing_dimension_closes_enriched_space": (
            missing_offset == expected_missing
        ),
        "direct_sum_full_rank": full_rank == int(enriched.dim),
        "missing_modes_are_trace_only": interior_leakage <= tolerance,
        "entity_embedding_orientation_equivariant": (
            maximum_equivariance_error <= tolerance
        ),
        "missing_entity_subspaces_orientation_invariant": (
            maximum_complement_invariance_error <= tolerance
        ),
        "induced_missing_transformations_unitary": (
            maximum_induced_unitarity_error <= tolerance
        ),
        "candidate_matrix_not_constructed": True,
        "no_inactive_p6_rows_retained_in_candidate_matrix": True,
    }
    passed = all(checks.values())
    if not passed:
        failed = [name for name, value in checks.items() if not value]
        raise RuntimeError(
            "missing-p6-trace complement audit failed: "
            + ", ".join(failed)
        )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.missing-p6-trace-entity-complement.v1"
            ),
            "status": "missing_p6_trace_entity_complement_pass",
            "pass": True,
            "canonical": False,
            "production_qualified": False,
            "ordinary_default_changed": False,
            "cell_type": "hexahedron",
            "trace_degree": trace_degree,
            "enriched_degree": enriched_degree,
            "retained_local_dimension": int(retained.dim),
            "enriched_local_dimension": int(enriched.dim),
            "retained_local_trace_dimension": int(
                sum(
                    len(entity)
                    for dimension in retained.entity_dofs[:3]
                    for entity in dimension
                )
            ),
            "enriched_local_trace_dimension": int(
                sum(
                    len(entity)
                    for dimension in enriched.entity_dofs[:3]
                    for entity in dimension
                )
            ),
            "missing_local_trace_dimension": missing_offset,
            "missing_edge_modes_per_entity": tuple(
                entity_missing_dimensions["edge"]
            ),
            "missing_face_modes_per_entity": tuple(
                entity_missing_dimensions["face"]
            ),
            "retained_embedding_rank": retained_rank,
            "direct_sum_rank": full_rank,
            "direct_sum_condition_number": full_condition_number,
            "missing_interior_leakage_max": interior_leakage,
            "entity_orientation_equivariance_error_max": (
                maximum_equivariance_error
            ),
            "missing_orientation_invariance_error_max": (
                maximum_complement_invariance_error
            ),
            "missing_induced_unitarity_error_max": (
                maximum_induced_unitarity_error
            ),
            "retained_to_enriched_sha256": _array_sha256(
                retained_to_enriched
            ),
            "missing_to_enriched_sha256": _array_sha256(
                missing_to_enriched
            ),
            "checks": checks,
            "candidate_matrix_constructed": False,
            "inactive_p6_rows_retained_in_candidate_matrix": False,
            "actual_dwr_indicator": False,
            "lane_b_formal_selection_authorized": False,
            "scope": (
                "reference-cell entity complement and orientation closure; "
                "global active numbering, periodic orbit closure, exact-"
                "sequence closure of a selected subset, and candidate "
                "assembly remain separate gates"
            ),
        }
    )
    return MissingP6TraceComplement(
        trace_degree=trace_degree,
        enriched_degree=enriched_degree,
        retained_dimension=int(retained.dim),
        enriched_dimension=int(enriched.dim),
        missing_dimension=missing_offset,
        retained_to_enriched=retained_to_enriched,
        missing_to_enriched=missing_to_enriched,
        entity_blocks=tuple(blocks),
        audit=audit,
    )


def _relative_matrix_error(left: np.ndarray, right: np.ndarray) -> float:
    left_array = np.asarray(left)
    right_array = np.asarray(right)
    norm_order: str | int | None = (
        "fro" if left_array.ndim >= 2 else None
    )
    difference = float(
        np.linalg.norm(left_array - right_array, ord=norm_order)
    )
    scale = max(
        1.0,
        float(np.linalg.norm(left_array, ord=norm_order)),
        float(np.linalg.norm(right_array, ord=norm_order)),
    )
    return difference / scale


def _spectral_riesz_factors(
    gram: np.ndarray,
    *,
    tolerance: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    matrix = np.asarray(gram, dtype=np.complex128)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("trace Gram matrix must be square")
    if matrix.shape[0] == 0:
        raise ValueError("trace Gram matrix must be nonempty")
    if not np.all(np.isfinite(matrix)):
        raise FloatingPointError("trace Gram matrix contains NaN or Inf")
    hermitian_error = _relative_matrix_error(matrix, matrix.conj().T)
    if hermitian_error > tolerance:
        raise ValueError("trace Gram matrix is not Hermitian")
    matrix = 0.5 * (matrix + matrix.conj().T)
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    maximum = float(np.max(eigenvalues))
    minimum = float(np.min(eigenvalues))
    if (
        not np.all(np.isfinite(eigenvalues))
        or maximum <= 0.0
        or minimum <= tolerance * maximum
    ):
        raise ValueError(
            "trace Gram matrix is not numerically positive definite"
        )
    sqrt_values = np.sqrt(eigenvalues)
    inverse_sqrt_values = 1.0 / sqrt_values
    sqrt = (eigenvectors * sqrt_values) @ eigenvectors.conj().T
    inverse_sqrt = (
        eigenvectors * inverse_sqrt_values
    ) @ eigenvectors.conj().T
    return matrix, sqrt, inverse_sqrt, eigenvalues


def whiten_trace_dual_covectors(
    gram: np.ndarray,
    dual_covectors: np.ndarray,
    *,
    tolerance: float = 5.0e-12,
) -> WhitenedTraceDualCovectors:
    """Whiten dual covectors using a Hermitian positive trace Gram matrix.

    If trace basis columns change as ``B_new = B S``, Galerkin residual
    covectors change as ``r_new = S**H r`` and the Gram matrix changes as
    ``G_new = S**H G S``.  Consequently ``r**H G**-1 r`` and all singular
    values returned here are invariant under arbitrary nonsingular rotations
    *and scalings*, up to roundoff.  Individual whitened coordinates may still
    rotate unitarily and must never be ranked as physical modes.
    """

    tolerance = float(tolerance)
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("Riesz tolerance must be positive and finite")
    matrix, _sqrt, inverse_sqrt, _eigenvalues = _spectral_riesz_factors(
        gram,
        tolerance=tolerance,
    )
    covectors = np.asarray(dual_covectors, dtype=np.complex128)
    if covectors.ndim == 1:
        covectors = covectors[:, None]
    if covectors.ndim != 2 or covectors.shape[0] != matrix.shape[0]:
        raise ValueError(
            "dual covectors must have shape (trace modes, goals)"
        )
    if covectors.shape[1] == 0:
        raise ValueError("at least one dual covector is required")
    if not np.all(np.isfinite(covectors)):
        raise FloatingPointError("trace dual covectors contain NaN or Inf")
    whitened = inverse_sqrt @ covectors
    dual_goal_gram = whitened.conj().T @ whitened
    singular_values = np.linalg.svd(
        whitened,
        compute_uv=False,
        full_matrices=False,
    )
    finite = bool(
        np.all(np.isfinite(whitened))
        and np.all(np.isfinite(dual_goal_gram))
        and np.all(np.isfinite(singular_values))
    )
    if not finite:
        raise FloatingPointError(
            "trace Riesz whitening produced NaN or Inf"
        )
    reconstruction_error = _relative_matrix_error(
        dual_goal_gram,
        covectors.conj().T @ np.linalg.solve(matrix, covectors),
    )
    if reconstruction_error > 50.0 * tolerance:
        raise RuntimeError("trace Riesz whitening reconstruction failed")
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.missing-trace-dual-riesz-whitening.v1"
            ),
            "pass": True,
            "trace_mode_count": int(matrix.shape[0]),
            "goal_column_count": int(covectors.shape[1]),
            "dual_goal_gram_reconstruction_relative_error": (
                reconstruction_error
            ),
            "basis_rotation_scaling_invariant_quantities": (
                "dual_goal_gram",
                "singular_values",
            ),
            "individual_whitened_coordinates_basis_invariant": False,
            "coordinatewise_missing_mode_ranking_authorized": False,
            "entity_orbit_ranking_authorized": False,
            "actual_dwr_indicator": False,
            "lane_b_formal_selection_authorized": False,
        }
    )
    return WhitenedTraceDualCovectors(
        whitened_covectors=whitened,
        dual_goal_gram=dual_goal_gram,
        singular_values=singular_values,
        audit=audit,
    )


def audit_trace_riesz_basis_change(
    gram: np.ndarray,
    dual_covectors: np.ndarray,
    change_of_basis: np.ndarray,
    *,
    tolerance: float = 5.0e-12,
) -> Mapping[str, Any]:
    """Audit a nonsingular trace-basis rotation/scaling transformation."""

    matrix = np.asarray(gram, dtype=np.complex128)
    change = np.asarray(change_of_basis, dtype=np.complex128)
    covectors = np.asarray(dual_covectors, dtype=np.complex128)
    if covectors.ndim == 1:
        covectors = covectors[:, None]
    if (
        change.ndim != 2
        or change.shape[0] != change.shape[1]
        or change.shape != matrix.shape
    ):
        raise ValueError("trace change of basis has the wrong shape")
    if not np.all(np.isfinite(change)):
        raise FloatingPointError(
            "trace change of basis contains NaN or Inf"
        )
    singular_values = np.linalg.svd(change, compute_uv=False)
    if (
        not np.all(np.isfinite(singular_values))
        or float(np.min(singular_values))
        <= tolerance * float(np.max(singular_values))
    ):
        raise ValueError("trace change of basis is numerically singular")
    original = whiten_trace_dual_covectors(
        matrix,
        covectors,
        tolerance=tolerance,
    )
    transformed_gram = change.conj().T @ matrix @ change
    transformed_covectors = change.conj().T @ covectors
    transformed = whiten_trace_dual_covectors(
        transformed_gram,
        transformed_covectors,
        tolerance=tolerance,
    )
    goal_gram_error = _relative_matrix_error(
        original.dual_goal_gram,
        transformed.dual_goal_gram,
    )
    singular_value_error = _relative_matrix_error(
        original.singular_values,
        transformed.singular_values,
    )
    passed = bool(
        goal_gram_error <= 100.0 * tolerance
        and singular_value_error <= 100.0 * tolerance
    )
    if not passed:
        raise RuntimeError(
            "trace Riesz basis rotation/scaling invariance audit failed"
        )
    return MappingProxyType(
        {
            "schema_version": (
                "task035b.trace-riesz-basis-change-audit.v1"
            ),
            "pass": True,
            "change_condition_number": float(
                np.max(singular_values) / np.min(singular_values)
            ),
            "dual_goal_gram_relative_error": goal_gram_error,
            "singular_values_relative_error": singular_value_error,
            "arbitrary_nonsingular_rotation_scaling_invariance": True,
            "coordinatewise_mode_invariance": False,
            "coordinatewise_missing_mode_ranking_authorized": False,
        }
    )


def _reference_entity_quadrature(
    *,
    entity_dimension: int,
    local_entity_index: int,
    quadrature_degree: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    geometry = np.asarray(
        basix.geometry(basix.CellType.hexahedron),
        dtype=np.float64,
    )
    topology = basix.topology(basix.CellType.hexahedron)
    vertices = geometry[
        np.asarray(
            topology[entity_dimension][local_entity_index],
            dtype=np.int32,
        )
    ]
    if entity_dimension == 1:
        entity_points, entity_weights = basix.make_quadrature(
            basix.CellType.interval,
            quadrature_degree,
        )
        tangent = vertices[1] - vertices[0]
        measure = float(np.linalg.norm(tangent))
        unit_tangent = tangent / measure
        points = (
            vertices[0]
            + np.asarray(entity_points)[:, 0, None] * tangent
        )
        projector = np.outer(unit_tangent, unit_tangent)
    elif entity_dimension == 2:
        entity_points, entity_weights = basix.make_quadrature(
            basix.CellType.quadrilateral,
            quadrature_degree,
        )
        tangent_0 = vertices[1] - vertices[0]
        tangent_1 = vertices[2] - vertices[0]
        tangents = np.column_stack((tangent_0, tangent_1))
        measure = float(
            np.linalg.norm(np.cross(tangent_0, tangent_1))
        )
        points = (
            vertices[0]
            + np.asarray(entity_points)[:, 0, None] * tangent_0
            + np.asarray(entity_points)[:, 1, None] * tangent_1
        )
        projector = (
            tangents
            @ np.linalg.inv(tangents.T @ tangents)
            @ tangents.T
        )
    else:
        raise ValueError("missing trace Riesz entities must be edges or faces")
    weights = np.asarray(entity_weights, dtype=np.float64) * measure
    return points, weights, projector


def _deterministic_basis_change_and_covectors(
    dimension: int,
) -> tuple[np.ndarray, np.ndarray]:
    indices = np.arange(dimension, dtype=np.float64)
    raw = (
        np.sin((indices[:, None] + 1.0) * (indices[None, :] + 1.5))
        + np.cos((indices[:, None] + 0.5) * (indices[None, :] + 2.0))
    )
    orthogonal, _upper = np.linalg.qr(raw)
    scales = np.geomspace(0.5, 2.0, dimension)
    change = orthogonal @ np.diag(scales)
    columns = np.arange(1, 5, dtype=np.float64)[None, :]
    covectors = (
        np.sin((indices[:, None] + 1.0) * columns)
        + 1j
        * np.cos((indices[:, None] + 0.75) * (columns + 0.5))
    )
    return change, covectors


def build_missing_p6_trace_riesz_metric(
    complement: MissingP6TraceComplement | None = None,
    *,
    quadrature_degree: int = 16,
    tolerance: float = 5.0e-12,
) -> MissingP6TraceRieszMetric:
    """Build reference-entity tangential-L2 direct-sum Gram/Riesz blocks.

    This is a lightweight reference-cell result.  It does not include the
    cross-entity trace couplings, actual mesh Jacobian/Piola maps, material
    scaling, shared-entity assembly, periodic-orbit closure, or Floquet phase
    pullbacks.  Therefore it proves the entity-local algebra needed for
    physical Riesz whitening but does not itself authorize a Lane B candidate
    or any residual/DWR ranking.
    """

    quadrature_degree = int(quadrature_degree)
    tolerance = float(tolerance)
    if quadrature_degree < 14:
        raise ValueError(
            "p6 trace Gram quadrature degree must be at least 14"
        )
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("Riesz tolerance must be positive and finite")
    if complement is None:
        complement = build_missing_p6_trace_complement()
    if (
        complement.trace_degree != 5
        or complement.enriched_degree != 6
        or complement.missing_dimension != 132
        or complement.audit.get("pass") is not True
    ):
        raise ValueError("unqualified p5/p6 missing trace complement")

    enriched = basix.ufl.element(
        "N1curl",
        "hexahedron",
        complement.enriched_degree,
    ).basix_element
    block_diagonal = np.zeros(
        (complement.missing_dimension, complement.missing_dimension),
        dtype=np.complex128,
    )
    blocks: list[MissingTraceEntityRieszBlock] = []
    minimum_eigenvalue = np.inf
    maximum_eigenvalue = 0.0
    maximum_condition_number = 0.0
    maximum_orientation_error = 0.0
    maximum_sqrt_error = 0.0
    maximum_inverse_sqrt_error = 0.0
    maximum_basis_goal_gram_error = 0.0
    maximum_basis_singular_value_error = 0.0

    for entity in complement.entity_blocks:
        points, weights, projector = _reference_entity_quadrature(
            entity_dimension=entity.entity_dimension,
            local_entity_index=entity.local_entity_index,
            quadrature_degree=quadrature_degree,
        )
        tabulated = np.asarray(
            enriched.tabulate(0, points),
            dtype=np.float64,
        )[0][:, entity.enriched_entity_dofs, :]
        values = np.einsum(
            "piv,ij->pjv",
            tabulated,
            entity.missing_embedding,
        )
        gram = np.einsum(
            "p,pia,ab,pjb->ij",
            weights,
            values.conj(),
            projector,
            values,
        )
        matrix, sqrt, inverse_sqrt, eigenvalues = (
            _spectral_riesz_factors(gram, tolerance=tolerance)
        )
        identity = np.eye(entity.missing_dimension, dtype=np.complex128)
        sqrt_error = _relative_matrix_error(sqrt @ sqrt, matrix)
        inverse_sqrt_error = _relative_matrix_error(
            inverse_sqrt @ matrix @ inverse_sqrt,
            identity,
        )
        orientation_error = 0.0
        for transformation in entity.induced_transformations:
            oriented = (
                transformation.conj().T
                @ matrix
                @ transformation
            )
            orientation_error = max(
                orientation_error,
                _relative_matrix_error(oriented, matrix),
            )
        change, covectors = _deterministic_basis_change_and_covectors(
            entity.missing_dimension
        )
        basis_audit = audit_trace_riesz_basis_change(
            matrix,
            covectors,
            change,
            tolerance=tolerance,
        )
        condition_number = float(
            np.max(eigenvalues) / np.min(eigenvalues)
        )
        block_checks = {
            "finite_positive_definite": bool(
                np.all(np.isfinite(eigenvalues))
                and float(np.min(eigenvalues)) > 0.0
            ),
            "sqrt_reconstructs_gram": (
                sqrt_error <= 50.0 * tolerance
            ),
            "dual_inverse_sqrt_whitens_gram": (
                inverse_sqrt_error <= 50.0 * tolerance
            ),
            "entity_orientation_is_metric_isometry": (
                orientation_error <= 100.0 * tolerance
            ),
            "arbitrary_basis_rotation_scaling_invariant": (
                basis_audit["pass"] is True
            ),
        }
        if not all(block_checks.values()):
            failed = [
                name for name, passed in block_checks.items() if not passed
            ]
            raise RuntimeError(
                "missing trace entity Riesz audit failed for "
                f"({entity.entity_dimension}, "
                f"{entity.local_entity_index}): {', '.join(failed)}"
            )
        start = entity.missing_column_start
        stop = entity.missing_column_stop
        block_diagonal[start:stop, start:stop] = matrix
        block_audit = MappingProxyType(
            {
                "schema_version": (
                    "task035b.reference-entity-trace-riesz-block.v1"
                ),
                "pass": True,
                "canonical": False,
                "production_qualified": False,
                "metric": "reference_entity_tangential_l2_direct_sum",
                "entity_dimension": entity.entity_dimension,
                "local_entity_index": entity.local_entity_index,
                "dimension": entity.missing_dimension,
                "quadrature_degree": quadrature_degree,
                "minimum_eigenvalue": float(np.min(eigenvalues)),
                "maximum_eigenvalue": float(np.max(eigenvalues)),
                "condition_number": condition_number,
                "sqrt_reconstruction_relative_error": sqrt_error,
                "dual_whitening_relative_error": inverse_sqrt_error,
                "orientation_metric_isometry_relative_error_max": (
                    orientation_error
                ),
                "basis_change_audit": dict(basis_audit),
                "gram_sha256": _array_sha256(matrix),
                "dual_inverse_sqrt_sha256": _array_sha256(
                    inverse_sqrt
                ),
                "checks": block_checks,
            }
        )
        blocks.append(
            MissingTraceEntityRieszBlock(
                entity_dimension=entity.entity_dimension,
                local_entity_index=entity.local_entity_index,
                missing_column_start=start,
                missing_column_stop=stop,
                gram=matrix,
                sqrt=sqrt,
                dual_inverse_sqrt=inverse_sqrt,
                eigenvalues=eigenvalues,
                quadrature_degree=quadrature_degree,
                audit=block_audit,
            )
        )
        minimum_eigenvalue = min(
            minimum_eigenvalue,
            float(np.min(eigenvalues)),
        )
        maximum_eigenvalue = max(
            maximum_eigenvalue,
            float(np.max(eigenvalues)),
        )
        maximum_condition_number = max(
            maximum_condition_number,
            condition_number,
        )
        maximum_orientation_error = max(
            maximum_orientation_error,
            orientation_error,
        )
        maximum_sqrt_error = max(maximum_sqrt_error, sqrt_error)
        maximum_inverse_sqrt_error = max(
            maximum_inverse_sqrt_error,
            inverse_sqrt_error,
        )
        maximum_basis_goal_gram_error = max(
            maximum_basis_goal_gram_error,
            float(basis_audit["dual_goal_gram_relative_error"]),
        )
        maximum_basis_singular_value_error = max(
            maximum_basis_singular_value_error,
            float(basis_audit["singular_values_relative_error"]),
        )

    checks = {
        "all_18_edge_face_entity_blocks_present": len(blocks) == 18,
        "block_dimensions_close_132_modes": (
            sum(block.missing_dimension for block in blocks) == 132
        ),
        "block_diagonal_gram_full_rank": (
            int(np.linalg.matrix_rank(block_diagonal)) == 132
        ),
        "all_blocks_positive_definite": minimum_eigenvalue > 0.0,
        "all_orientation_maps_metric_isometries": (
            maximum_orientation_error <= 100.0 * tolerance
        ),
        "all_dual_whitening_reconstructions_pass": (
            maximum_inverse_sqrt_error <= 50.0 * tolerance
        ),
        "basis_rotation_scaling_invariance_proved_numerically": (
            maximum_basis_goal_gram_error <= 100.0 * tolerance
            and maximum_basis_singular_value_error <= 100.0 * tolerance
        ),
        "candidate_matrix_not_constructed": True,
        "actual_global_residual_not_claimed": True,
        "actual_dwr_not_claimed": True,
        "ranking_not_authorized": True,
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "missing-p6-trace Riesz metric audit failed: "
            + ", ".join(failed)
        )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.reference-cell-missing-trace-riesz.v1"
            ),
            "status": "reference_entity_trace_riesz_pass",
            "pass": True,
            "canonical": False,
            "production_qualified": False,
            "metric": "reference_entity_tangential_l2_direct_sum",
            "metric_scope": "reference_cell_only",
            "quadrature_degree": quadrature_degree,
            "polynomial_product_exactness_degree_required": 12,
            "quadrature_exactness_margin": quadrature_degree - 12,
            "entity_block_count": len(blocks),
            "edge_block_count": sum(
                block.entity_dimension == 1 for block in blocks
            ),
            "face_block_count": sum(
                block.entity_dimension == 2 for block in blocks
            ),
            "missing_trace_dimension": complement.missing_dimension,
            "minimum_block_eigenvalue": minimum_eigenvalue,
            "maximum_block_eigenvalue": maximum_eigenvalue,
            "maximum_block_condition_number": maximum_condition_number,
            "sqrt_reconstruction_relative_error_max": maximum_sqrt_error,
            "dual_whitening_relative_error_max": (
                maximum_inverse_sqrt_error
            ),
            "orientation_metric_isometry_relative_error_max": (
                maximum_orientation_error
            ),
            "basis_change_dual_goal_gram_relative_error_max": (
                maximum_basis_goal_gram_error
            ),
            "basis_change_singular_values_relative_error_max": (
                maximum_basis_singular_value_error
            ),
            "block_diagonal_gram_sha256": _array_sha256(
                block_diagonal
            ),
            "basis_rotation_scaling_invariant": True,
            "individual_whitened_coordinates_basis_invariant": False,
            "cross_entity_trace_gram_couplings_included": False,
            "physical_mesh_riesz_metric_available": False,
            "physical_mesh_riesz_metric_status": (
                "controlled_stop_missing_actual_mesh_pullbacks"
            ),
            "physical_mesh_riesz_metric_missing_inputs": (
                "cross-entity trace Gram couplings",
                "cell Jacobian and Hcurl Piola maps",
                "physical entity measures",
                "shared active entity numbering",
                "periodic entity orbits",
                "orientation and Floquet phase pullbacks",
            ),
            "actual_global_missing_trace_residual_available": False,
            "periodic_orbit_svd_qr_performed": False,
            "coordinatewise_missing_mode_ranking_authorized": False,
            "entity_orbit_ranking_authorized": False,
            "actual_dwr_indicator": False,
            "lane_b_formal_selection_authorized": False,
            "candidate_matrix_constructed": False,
            "ordinary_default_changed": False,
            "checks": checks,
        }
    )
    return MissingP6TraceRieszMetric(
        trace_degree=complement.trace_degree,
        enriched_degree=complement.enriched_degree,
        missing_dimension=complement.missing_dimension,
        block_diagonal_gram=block_diagonal,
        entity_blocks=tuple(blocks),
        audit=audit,
    )


def prepare_periodic_orbit_svd_qr_payload(
    gram: np.ndarray,
    pulled_back_dual_covectors: np.ndarray,
    *,
    orbit_id: str,
    orbit_member_ids: Sequence[int],
    goal_labels: Sequence[str],
    actual_global_residual: bool,
    periodic_orbit_closed: bool,
    orientation_phase_pullbacks_verified: bool,
    physical_entity_gram_verified: bool,
    tolerance: float = 5.0e-12,
) -> WhitenedTraceDualCovectors:
    """Fail-closed future interface for periodic-orbit SVD/QR inputs.

    The caller must first pull every member covector to one representative
    physical entity, including orientation and Floquet phase.  This function
    exposes an invariant goal Gram matrix and singular values.  A future
    column-pivoted QR may act on the *goal columns* because left-unitary
    whitening changes do not affect their Gram matrix.  QR over individual
    trace coordinate axes remains forbidden.
    """

    gates = {
        "nonempty_orbit_id": bool(str(orbit_id)),
        "unique_nonempty_orbit_members": (
            len(tuple(orbit_member_ids)) > 0
            and len(set(map(int, orbit_member_ids)))
            == len(tuple(orbit_member_ids))
        ),
        "exact_review_v1_goal_labels": (
            tuple(map(str, goal_labels))
            == REVIEW_V1_MISSING_TRACE_GOAL_LABELS
        ),
        "actual_global_residual": actual_global_residual is True,
        "periodic_orbit_closed": periodic_orbit_closed is True,
        "orientation_phase_pullbacks_verified": (
            orientation_phase_pullbacks_verified is True
        ),
        "physical_entity_gram_verified": (
            physical_entity_gram_verified is True
        ),
    }
    if not all(gates.values()):
        failed = [name for name, passed in gates.items() if not passed]
        raise RuntimeError(
            "periodic-orbit trace SVD/QR gate failed: "
            + ", ".join(failed)
        )
    result = whiten_trace_dual_covectors(
        gram,
        pulled_back_dual_covectors,
        tolerance=tolerance,
    )
    if result.whitened_covectors.shape[1] != len(
        REVIEW_V1_MISSING_TRACE_GOAL_LABELS
    ):
        raise ValueError(
            "periodic-orbit trace payload requires exactly 16 goal columns"
        )
    return result


def split_enriched_local_operator(
    enriched_tensor: np.ndarray,
    retained_to_enriched: np.ndarray,
    missing_to_enriched: np.ndarray,
) -> dict[str, np.ndarray]:
    """Galerkin-split one oriented p6 cell tensor without global rows."""

    operator = np.asarray(enriched_tensor, dtype=np.complex128)
    retained = np.asarray(retained_to_enriched, dtype=np.complex128)
    missing = np.asarray(missing_to_enriched, dtype=np.complex128)
    if operator.ndim != 2 or operator.shape[0] != operator.shape[1]:
        raise ValueError("enriched tensor must be square")
    if (
        retained.ndim != 2
        or missing.ndim != 2
        or retained.shape[0] != operator.shape[0]
        or missing.shape[0] != operator.shape[0]
    ):
        raise ValueError(
            "retained/missing embeddings do not match the enriched tensor"
        )
    if retained.shape[1] + missing.shape[1] != operator.shape[0]:
        raise ValueError("retained and missing dimensions do not close")
    return {
        "retained_retained": retained.conj().T @ operator @ retained,
        "retained_missing": retained.conj().T @ operator @ missing,
        "missing_retained": missing.conj().T @ operator @ retained,
        "missing_missing": missing.conj().T @ operator @ missing,
    }


def _validate_vector_layout(
    vector: PETSc.Vec,
    reference: PETSc.Vec,
    *,
    label: str,
) -> None:
    if int(vector.getSize()) != int(reference.getSize()):
        raise ValueError(f"{label} global size differs")
    if int(vector.getLocalSize()) != int(reference.getLocalSize()):
        raise ValueError(f"{label} local size differs")
    if tuple(map(int, vector.getOwnershipRange())) != tuple(
        map(int, reference.getOwnershipRange())
    ):
        raise ValueError(f"{label} ownership range differs")


class MissingTraceResidualDiagnostic:
    """Exact missing-block residuals with an explicitly non-DWR proxy."""

    def __init__(
        self,
        *,
        missing_from_retained: PETSc.Mat,
        retained_from_missing: PETSc.Mat,
        retained_state: PETSc.Vec,
        missing_right_hand_side: PETSc.Vec,
    ) -> None:
        """Build ``r_H = b_H - A_HL x_L`` without a candidate matrix."""

        retained_rows = int(retained_from_missing.getSize()[0])
        missing_columns = int(retained_from_missing.getSize()[1])
        missing_rows = int(missing_from_retained.getSize()[0])
        retained_columns = int(missing_from_retained.getSize()[1])
        if retained_rows != retained_columns:
            raise ValueError("retained block dimensions do not close")
        if missing_rows != missing_columns:
            raise ValueError("missing block dimensions do not close")
        missing_comm = missing_from_retained.getComm().tompi4py()
        retained_comm = retained_from_missing.getComm().tompi4py()
        communicator_relation = MPI.Comm.Compare(
            missing_comm,
            retained_comm,
        )
        if communicator_relation not in {MPI.IDENT, MPI.CONGRUENT}:
            raise ValueError(
                "missing-trace block communicators are not congruent"
            )
        retained_layout = missing_from_retained.createVecRight()
        missing_layout = missing_from_retained.createVecLeft()
        retained_adjoint_layout = retained_from_missing.createVecLeft()
        missing_adjoint_layout = retained_from_missing.createVecRight()
        try:
            _validate_vector_layout(
                retained_state,
                retained_layout,
                label="retained state",
            )
            _validate_vector_layout(
                missing_right_hand_side,
                missing_layout,
                label="missing right-hand side",
            )
            _validate_vector_layout(
                retained_adjoint_layout,
                retained_layout,
                label="retained matrix layout",
            )
            _validate_vector_layout(
                missing_adjoint_layout,
                missing_layout,
                label="missing matrix layout",
            )
        finally:
            retained_layout.destroy()
            missing_layout.destroy()
            retained_adjoint_layout.destroy()
            missing_adjoint_layout.destroy()

        action = missing_from_retained.createVecLeft()
        missing_from_retained.mult(retained_state, action)
        primal_residual = missing_right_hand_side.copy()
        primal_residual.axpy(PETSc.ScalarType(-1.0), action)
        action.destroy()

        self._missing_from_retained = missing_from_retained
        self._retained_from_missing = retained_from_missing
        self._primal_residual = primal_residual
        self._retained_rows = retained_rows
        self._missing_rows = missing_rows
        self._goal_reports: dict[str, dict[str, Any]] = {}
        self._destroyed = False
        self._comm = missing_comm

    @property
    def primal_residual(self) -> PETSc.Vec:
        if self._destroyed:
            raise RuntimeError("missing-trace residual context was destroyed")
        return self._primal_residual

    def evaluate_adjoint(
        self,
        *,
        label: str,
        retained_adjoint: PETSc.Vec,
        reference_band: float,
        missing_goal_gradient: PETSc.Vec | None = None,
        residual_observer: (
            Callable[[PETSc.Vec, PETSc.Vec, Mapping[str, Any]], None]
            | None
        ) = None,
    ) -> dict[str, Any]:
        """Compute ``q_H = g_H - A_LH^H z_L`` for one real goal."""

        if self._destroyed:
            raise RuntimeError("missing-trace residual context was destroyed")
        label = str(label)
        if not label:
            raise ValueError("goal label must be non-empty")
        if label in self._goal_reports:
            raise ValueError(f"duplicate missing-trace goal label: {label}")
        reference_band = float(reference_band)
        if not np.isfinite(reference_band) or reference_band <= 0.0:
            raise ValueError("reference band must be positive and finite")

        retained_layout = self._retained_from_missing.createVecLeft()
        missing_layout = self._retained_from_missing.createVecRight()
        try:
            _validate_vector_layout(
                retained_adjoint,
                retained_layout,
                label="retained adjoint",
            )
            if missing_goal_gradient is not None:
                _validate_vector_layout(
                    missing_goal_gradient,
                    missing_layout,
                    label="missing goal gradient",
                )
        finally:
            retained_layout.destroy()
            missing_layout.destroy()

        adjoint_action = self._retained_from_missing.createVecRight()
        self._retained_from_missing.multHermitian(
            retained_adjoint,
            adjoint_action,
        )
        if missing_goal_gradient is None:
            adjoint_residual = adjoint_action.duplicate()
            adjoint_residual.set(PETSc.ScalarType(0.0))
        else:
            adjoint_residual = missing_goal_gradient.copy()
        adjoint_residual.axpy(PETSc.ScalarType(-1.0), adjoint_action)
        adjoint_action.destroy()

        primal_owned = np.asarray(
            self._primal_residual.getArray(readonly=True),
            dtype=np.complex128,
        )
        adjoint_owned = np.asarray(
            adjoint_residual.getArray(readonly=True),
            dtype=np.complex128,
        )
        locally_finite = bool(
            np.all(np.isfinite(primal_owned))
            and np.all(np.isfinite(adjoint_owned))
        )
        if not self._comm.allreduce(locally_finite, op=MPI.LAND):
            adjoint_residual.destroy()
            raise FloatingPointError(
                "missing-trace residual diagnostic contains NaN or Inf"
            )
        paired_owned = np.conj(adjoint_owned) * primal_owned
        local_l1 = float(np.sum(np.abs(paired_owned)))
        local_real = float(np.sum(paired_owned.real))
        local_imag = float(np.sum(paired_owned.imag))
        local_max = float(np.max(np.abs(paired_owned), initial=0.0))
        paired_l1 = float(self._comm.allreduce(local_l1, op=MPI.SUM))
        paired_real = float(self._comm.allreduce(local_real, op=MPI.SUM))
        paired_imag = float(self._comm.allreduce(local_imag, op=MPI.SUM))
        paired_max = float(self._comm.allreduce(local_max, op=MPI.MAX))
        primal_norm = float(self._primal_residual.norm())
        adjoint_norm = float(adjoint_residual.norm())
        paired_inner_abs = float(
            abs(complex(paired_real, paired_imag))
        )
        cauchy_bound = float(primal_norm * adjoint_norm)
        finite_metrics = all(
            np.isfinite(value)
            for value in (
                paired_l1,
                paired_real,
                paired_imag,
                paired_max,
                primal_norm,
                adjoint_norm,
                paired_inner_abs,
                cauchy_bound,
            )
        )
        if not finite_metrics:
            adjoint_residual.destroy()
            raise FloatingPointError(
                "missing-trace residual metrics contain NaN or Inf"
            )
        report = {
            "schema_version": (
                "task035b.missing-p6-trace-residual-pair.v1"
            ),
            "status": "actual_missing_trace_residual_pair_proxy_only",
            "pass": True,
            "goal_label": label,
            "retained_rows": self._retained_rows,
            "missing_trace_rows": self._missing_rows,
            "reference_band": reference_band,
            "primal_residual_norm": primal_norm,
            "adjoint_residual_norm": adjoint_norm,
            "paired_residual_l1": paired_l1,
            "paired_residual_real_sum": paired_real,
            "paired_residual_imag_sum": paired_imag,
            "paired_residual_max_abs": paired_max,
            "rotation_invariant_paired_inner_product_abs": (
                paired_inner_abs
            ),
            "rotation_invariant_cauchy_bound": cauchy_bound,
            "normalized_rotation_invariant_inner_product_proxy": (
                paired_inner_abs / reference_band
            ),
            "normalized_rotation_invariant_cauchy_bound_proxy": (
                cauchy_bound / reference_band
            ),
            "normalized_paired_residual_l1_proxy": (
                paired_l1 / reference_band
            ),
            "paired_residual_l1_is_coordinate_dependent": True,
            "coordinatewise_missing_mode_ranking_authorized": False,
            "entity_orbit_ranking_authorized": False,
            "rotation_invariant_metrics": [
                "primal_residual_norm",
                "adjoint_residual_norm",
                "rotation_invariant_paired_inner_product_abs",
                "rotation_invariant_cauchy_bound",
            ],
            "actual_missing_trace_primal_residual": True,
            "actual_missing_trace_adjoint_residual": True,
            "residual_weighted": True,
            "estimator": "unpreconditioned_paired_residual_proxy",
            "actual_dwr_indicator": False,
            "lane_b_formal_selection_authorized": False,
            "dwr_unavailable_reason": (
                "the missing-trace complement correction/inverse has not "
                "been solved; coordinate-wise q_H^H r_H is basis-scaled "
                "and is not a DWR error representation"
            ),
            "candidate_matrix_constructed": False,
            "inactive_p6_rows_retained_in_candidate_matrix": False,
            "ordinary_default_changed": False,
        }
        try:
            if residual_observer is not None:
                residual_observer(
                    self._primal_residual,
                    adjoint_residual,
                    MappingProxyType(report),
                )
        finally:
            adjoint_residual.destroy()
        self._goal_reports[label] = report
        return dict(report)

    def finalize(self) -> dict[str, Any]:
        """Return a compact fail-closed multi-goal residual report."""

        if self._destroyed:
            raise RuntimeError("missing-trace residual context was destroyed")
        expected_labels = set(REVIEW_V1_MISSING_TRACE_GOAL_LABELS)
        actual_labels = set(self._goal_reports)
        actual_count = len(self._goal_reports)
        if actual_labels != expected_labels:
            missing = sorted(expected_labels - actual_labels)
            unexpected = sorted(actual_labels - expected_labels)
            raise RuntimeError(
                "missing-trace residual Review V1 goal labels do not close: "
                f"missing={missing}, unexpected={unexpected}"
            )
        primal_owned = np.asarray(
            self._primal_residual.getArray(readonly=True),
            dtype=np.complex128,
        )
        locally_finite = bool(np.all(np.isfinite(primal_owned)))
        if not self._comm.allreduce(locally_finite, op=MPI.LAND):
            raise FloatingPointError(
                "missing-trace primal residual contains NaN or Inf at finalize"
            )
        primal_norm = float(self._primal_residual.norm())
        metric_names = (
            "reference_band",
            "primal_residual_norm",
            "adjoint_residual_norm",
            "paired_residual_l1",
            "paired_residual_real_sum",
            "paired_residual_imag_sum",
            "paired_residual_max_abs",
            "rotation_invariant_paired_inner_product_abs",
            "rotation_invariant_cauchy_bound",
            "normalized_rotation_invariant_inner_product_proxy",
            "normalized_rotation_invariant_cauchy_bound_proxy",
            "normalized_paired_residual_l1_proxy",
        )
        reports_finite = all(
            report.get("pass") is True
            and all(
                np.isfinite(float(report.get(name, np.nan)))
                for name in metric_names
            )
            for report in self._goal_reports.values()
        )
        if not (
            self._comm.allreduce(reports_finite, op=MPI.LAND)
            and np.isfinite(primal_norm)
        ):
            raise FloatingPointError(
                "missing-trace finalized metrics contain NaN or Inf"
            )
        return {
            "schema_version": (
                "task035b.missing-p6-trace-residual-diagnostic.v1"
            ),
            "status": "actual_16_goal_missing_trace_residuals_pass",
            "pass": True,
            "goal_count": actual_count,
            "expected_goal_count": len(REVIEW_V1_MISSING_TRACE_GOAL_LABELS),
            "expected_goal_labels": list(
                REVIEW_V1_MISSING_TRACE_GOAL_LABELS
            ),
            "retained_rows": self._retained_rows,
            "missing_trace_rows": self._missing_rows,
            "primal_residual_norm": primal_norm,
            "goals": {
                label: dict(report)
                for label, report in sorted(self._goal_reports.items())
            },
            "actual_missing_trace_primal_residual": True,
            "actual_missing_trace_adjoint_residual": True,
            "estimator": "unpreconditioned_paired_residual_proxy",
            "actual_dwr_indicator": False,
            "lane_b_formal_selection_authorized": False,
            "coordinatewise_missing_mode_ranking_authorized": False,
            "entity_orbit_ranking_authorized": False,
            "basis_invariant_riesz_metric_available": False,
            "basis_invariant_riesz_metric_missing_reason": (
                "this residual diagnostic has not been supplied an actual "
                "physical-cell/periodic-orbit trace Gram; the separate "
                "reference-entity direct-sum metric does not close that gate"
            ),
            "reference_entity_riesz_module_available": True,
            "reference_entity_riesz_applied_to_this_residual": False,
            "candidate_matrix_constructed": False,
            "inactive_p6_rows_retained_in_candidate_matrix": False,
            "ordinary_default_changed": False,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._primal_residual.destroy()
        self._destroyed = True

    def __enter__(self) -> MissingTraceResidualDiagnostic:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.destroy()


__all__ = [
    "MissingP6TraceComplement",
    "MissingP6TraceRieszMetric",
    "MissingTraceEntityBlock",
    "MissingTraceEntityRieszBlock",
    "MissingTraceResidualDiagnostic",
    "REVIEW_V1_MISSING_TRACE_GOAL_LABELS",
    "WhitenedTraceDualCovectors",
    "audit_trace_riesz_basis_change",
    "build_missing_p6_trace_complement",
    "build_missing_p6_trace_riesz_metric",
    "prepare_periodic_orbit_svd_qr_payload",
    "split_enriched_local_operator",
    "whiten_trace_dual_covectors",
]
