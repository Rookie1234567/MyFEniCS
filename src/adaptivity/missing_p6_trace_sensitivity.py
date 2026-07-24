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
from typing import Any, Callable, Mapping

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
                "no trace Gram/Riesz operator has been assembled; only "
                "unitary-rotation-invariant Euclidean residual metrics are "
                "reported"
            ),
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
    "MissingTraceEntityBlock",
    "MissingTraceResidualDiagnostic",
    "REVIEW_V1_MISSING_TRACE_GOAL_LABELS",
    "build_missing_p6_trace_complement",
    "split_enriched_local_operator",
]
