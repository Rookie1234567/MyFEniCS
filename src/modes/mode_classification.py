from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Sequence

import numpy as np
import ufl
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc
from scipy.optimize import linear_sum_assignment

from ..common.config_3d import SimulationConfig3D
from .cross_section_spaces import CrossSectionMesh, CrossSectionSpaces
from .quadratic_beta_eigenproblem import (
    EigenvectorOwnership,
    QuadraticBetaMode,
    QuadraticBetaOperators,
    QuadraticBetaSolveReport,
    quadratic_beta_polynomial_relative_residual,
    solve_quadratic_beta_modes,
)


ModeDirection = Literal["forward", "backward", "ambiguous"]
ModeKind = Literal[
    "propagating",
    "lossy_propagating",
    "evanescent",
    "cutoff_or_near_zero_flux",
]


class NoAdmissibleLeftPairError(RuntimeError):
    """Raised when the adjoint solve cannot pair every requested right mode."""

    def __init__(
        self,
        errors: Sequence[float],
        *,
        maximum_relative_error: float,
    ) -> None:
        self.pair_relative_errors = tuple(float(error) for error in errors)
        self.maximum_relative_error = float(maximum_relative_error)
        failures = [
            (index, error)
            for index, error in enumerate(self.pair_relative_errors)
            if not np.isfinite(error) or error > self.maximum_relative_error
        ]
        rendered = ", ".join(
            f"index={index}, error={error:.6e}" for index, error in failures
        )
        super().__init__(
            "Adjoint QEP candidate pool has no admissible conjugate partner "
            "for every right mode "
            f"(limit={self.maximum_relative_error:.6e}; {rendered})."
        )


class NearDegenerateBlockPartitionSplitError(RuntimeError):
    """Raised when independently normalized blocks still couple above Gate."""

    def __init__(self, audit: dict[str, object]) -> None:
        self.audit = dict(audit)
        super().__init__(
            "near_degenerate_block_partition_split: "
            f"cross_block_max={audit['max_cross_block_overlap']:.6e}, "
            f"limit={audit['block_rotation_tolerance']:.6e}, "
            f"indices={audit['worst_cross_block_indices']}"
        )


@dataclass(frozen=True)
class NearDegenerateGroup:
    indices: tuple[int, ...]
    beta_center: complex
    max_relative_beta_spread: float
    overlap_condition: float
    normalization_method: str
    post_normalization_identity_error: float


@dataclass
class ClassifiedBiorthogonalMode:
    beta: complex
    right: QuadraticBetaMode
    left_reduced: PETSc.Vec
    left_full: PETSc.Vec
    left_adjoint_beta: complex
    left_polynomial_relative_residual: float
    poynting_z_before_normalization: float
    poynting_z_after_normalization: float
    flux_tolerance: float
    kind: ModeKind
    direction: ModeDirection
    classification_basis: str
    passive_branch_valid: bool
    right_scale: float
    qprime_overlap_after: complex
    left_ownership: EigenvectorOwnership

    def destroy(self) -> None:
        self.right.destroy()
        self.left_reduced.destroy()
        self.left_full.destroy()


@dataclass
class BiorthogonalModeBasis:
    modes: list[ClassifiedBiorthogonalMode]
    groups: tuple[NearDegenerateGroup, ...]
    biorthogonality_matrix: np.ndarray
    max_identity_error: float
    max_entry_identity_error: float
    adjoint_solver_report: QuadraticBetaSolveReport
    left_pair_relative_errors: tuple[float, ...]
    full_vector_gathered: bool = False
    near_degenerate_partition_audit: dict[str, object] | None = None
    basis_origin: str = "independent_qep"
    basis_construction_audit: dict[str, object] | None = None

    def destroy(self) -> None:
        for mode in self.modes:
            mode.destroy()


@dataclass(frozen=True)
class ReciprocalModePair:
    positive_index: int
    negative_index: int
    relative_beta_error: float
    electric_mass_overlap: float
    opposite_direction: bool
    passive_branches_valid: bool


@dataclass(frozen=True)
class ModeTrackingMatch:
    previous_index: int
    current_index: int
    overlap: float
    relative_beta_change: float


@dataclass(frozen=True)
class SubspaceTrackingReport:
    previous_indices: tuple[int, ...]
    current_indices: tuple[int, ...]
    singular_values: tuple[float, ...]
    max_principal_angle_rad: float


@dataclass(frozen=True)
class ModeTrackingReport:
    matches: tuple[ModeTrackingMatch, ...]
    unmatched_previous: tuple[int, ...]
    unmatched_current: tuple[int, ...]
    subspaces: tuple[SubspaceTrackingReport, ...]
    overlap_matrix: np.ndarray


@dataclass(frozen=True)
class DirectionalModeSelectionReport:
    requested_modes: int
    candidate_modes: int
    selected_modes: int
    desired_direction: ModeDirection
    direction_counts: dict[str, int]
    passive_candidate_count: int
    selected_candidate_indices: tuple[int, ...]
    flux_tolerance: float
    finite_candidate_count: int
    numerically_infinite_candidate_count: int
    abs_beta_cutoff: float | None
    first_rejected_numerical_infinity_beta: complex | None


class PoyntingFluxEvaluator:
    """Evaluate impedance-scaled cross-section power without vector gathering."""

    def __init__(
        self,
        cfg: SimulationConfig3D,
        cross_section: CrossSectionMesh,
        spaces: CrossSectionSpaces,
    ) -> None:
        self._comm = cross_section.mesh.comm
        self._field = fem.Function(spaces.mixed, name="task032_cross_section_mode")
        self._beta = fem.Constant(
            cross_section.mesh, PETSc.ScalarType(0.0 + 0.0j)
        )
        Et, Ez = ufl.split(self._field)
        inverse_i_k_mu = 1.0 / (
            1j * float(cfg.k0) * complex(cfg.mu_r)
        )
        Hx = inverse_i_k_mu * (Ez.dx(1) - 1j * self._beta * Et[1])
        Hy = inverse_i_k_mu * (1j * self._beta * Et[0] - Ez.dx(0))
        integrand = 0.5 * (
            Et[0] * ufl.conj(Hy) - Et[1] * ufl.conj(Hx)
        )
        self._form = fem.form(integrand * ufl.dx)

    def evaluate(self, full_vector: PETSc.Vec, beta: complex) -> float:
        if int(full_vector.getSize()) != int(self._field.x.petsc_vec.getSize()):
            raise ValueError("Mode vector and mixed function space have different sizes.")
        full_vector.copy(self._field.x.petsc_vec)
        self._field.x.scatter_forward()
        self._beta.value = PETSc.ScalarType(beta)
        local_value = complex(fem.assemble_scalar(self._form))
        global_value = complex(self._comm.allreduce(local_value, op=MPI.SUM))
        return float(global_value.real)


def _adjoint_matrix(matrix: PETSc.Mat) -> PETSc.Mat:
    adjoint = PETSc.Mat()
    matrix.hermitianTranspose(adjoint)
    return adjoint


def _qep_overlap(
    operators: QuadraticBetaOperators,
    left: PETSc.Vec,
    beta_left: complex,
    right: PETSc.Vec,
    beta_right: complex,
) -> complex:
    action = operators.K1.createVecLeft()
    work = operators.K2.createVecLeft()
    operators.K1.mult(right, action)
    operators.K2.mult(right, work)
    action.axpy(beta_left + beta_right, work)
    # PETSc VecDot(x, y) returns y^H x.  Passing the action first therefore
    # evaluates left^H [K1 + (beta_l + beta_r) K2] right.
    value = complex(action.dot(left))
    action.destroy()
    work.destroy()
    return value


def _batched_left_dots(
    action: PETSc.Vec, left_vectors: Sequence[PETSc.Vec]
) -> np.ndarray:
    """Evaluate ``left^H action`` with extended-precision accumulation.

    PETSc stores the vectors in complex128, but a complex128 dot reduction can
    lose the small remainder when modal overlap terms cancel.  Accumulate each
    rank-local dot in ``clongdouble`` and reduce only the resulting scalar
    real/imaginary pairs in ``longdouble``.  This keeps vectors distributed
    while avoiding both local and cross-rank complex128 summation loss.
    """

    action_local = np.asarray(
        action.getArray(readonly=True), dtype=np.clongdouble
    )
    local_values = np.empty((len(left_vectors), 2), dtype=np.longdouble)
    for index, left in enumerate(left_vectors):
        left_local = np.asarray(
            left.getArray(readonly=True), dtype=np.clongdouble
        )
        if left_local.shape != action_local.shape:
            raise ValueError("Left and action vectors have different layouts.")
        value = np.sum(
            np.conj(left_local) * action_local,
            dtype=np.clongdouble,
        )
        local_values[index, 0] = value.real
        local_values[index, 1] = value.imag

    global_values = np.empty_like(local_values)
    action.getComm().tompi4py().Allreduce(
        local_values, global_values, op=MPI.SUM
    )
    return np.asarray(
        global_values[:, 0] + 1j * global_values[:, 1],
        dtype=np.complex128,
    )


def _qep_overlap_matrix(
    operators: QuadraticBetaOperators,
    left_betas: Sequence[complex],
    right_betas: Sequence[complex],
    left_vectors: Sequence[PETSc.Vec],
    right_vectors: Sequence[PETSc.Vec],
) -> np.ndarray:
    """Build the divided-difference overlap with O(M) sparse MatMults.

    The previous elementwise implementation rebuilt ``K1 @ right`` and
    ``K2 @ right`` for every left/right pair, requiring O(M^2) sparse
    MatMults.  Reusing both actions per right mode reduces that work to O(M).
    Both dot-product accumulation and the final scalar combination use
    extended precision to avoid cancellation in
    ``K1 @ right + beta*K2 @ right``.
    """

    if len(left_betas) != len(left_vectors):
        raise ValueError("Left beta and vector counts differ.")
    if len(right_betas) != len(right_vectors):
        raise ValueError("Right beta and vector counts differ.")
    matrix = np.empty(
        (len(left_vectors), len(right_vectors)), dtype=np.complex128
    )
    for column, (beta_right, right) in enumerate(
        zip(right_betas, right_vectors)
    ):
        k1_action = operators.K1.createVecLeft()
        k2_action = operators.K2.createVecLeft()
        try:
            operators.K1.mult(right, k1_action)
            operators.K2.mult(right, k2_action)
            k1_overlaps = _batched_left_dots(k1_action, left_vectors)
            k2_overlaps = _batched_left_dots(k2_action, left_vectors)
            beta_sums = np.asarray(left_betas, dtype=np.clongdouble)
            beta_sums += np.clongdouble(beta_right)
            values = np.asarray(k1_overlaps, dtype=np.clongdouble)
            values += beta_sums * np.asarray(
                k2_overlaps, dtype=np.clongdouble
            )
            matrix[:, column] = np.asarray(values, dtype=np.complex128)
        finally:
            k1_action.destroy()
            k2_action.destroy()
    return matrix


def _electric_mass_overlap(
    mass: PETSc.Mat, first: PETSc.Vec, second: PETSc.Vec
) -> complex:
    action = mass.createVecLeft()
    mass.mult(second, action)
    # PETSc VecDot(x, y) returns y^H x.
    value = complex(action.dot(first))
    action.destroy()
    return value


def _normalized_mass_overlap(
    mass: PETSc.Mat, first: PETSc.Vec, second: PETSc.Vec
) -> float:
    cross = abs(_electric_mass_overlap(mass, first, second))
    norm_first = max(
        _electric_mass_overlap(mass, first, first).real, 0.0
    )
    norm_second = max(
        _electric_mass_overlap(mass, second, second).real, 0.0
    )
    return float(cross / max(np.sqrt(norm_first * norm_second), 1.0e-30))


def _left_relative_residual(
    adjoints: tuple[PETSc.Mat, PETSc.Mat, PETSc.Mat],
    beta: complex,
    left: PETSc.Vec,
) -> float:
    residual = adjoints[0].createVecLeft()
    work = adjoints[0].createVecLeft()
    adjoints[0].mult(left, residual)
    adjoints[1].mult(left, work)
    residual.axpy(np.conj(beta), work)
    adjoints[2].mult(left, work)
    residual.axpy(np.conj(beta) ** 2, work)
    numerator = float(residual.norm(PETSc.NormType.NORM_2))
    denominator = float(left.norm(PETSc.NormType.NORM_2)) * (
        float(adjoints[0].norm(PETSc.NormType.FROBENIUS))
        + abs(beta) * float(adjoints[1].norm(PETSc.NormType.FROBENIUS))
        + abs(beta) ** 2 * float(adjoints[2].norm(PETSc.NormType.FROBENIUS))
    )
    residual.destroy()
    work.destroy()
    return numerator / max(denominator, 1.0e-30)


def _relative_beta_distance(first: complex, second: complex) -> float:
    return float(abs(first - second) / max(abs(first), abs(second), 1.0e-12))


def _require_admissible_left_pairs(
    errors: Sequence[float], *, maximum_relative_error: float
) -> None:
    """Reject incomplete adjoint candidate pools before vector normalization."""

    limit = float(maximum_relative_error)
    if not np.isfinite(limit) or limit < 0.0:
        raise ValueError(
            "Maximum left/right beta pair relative error must be finite and "
            "non-negative."
        )
    if any(
        not np.isfinite(error) or float(error) > limit for error in errors
    ):
        raise NoAdmissibleLeftPairError(
            errors,
            maximum_relative_error=limit,
        )


def _near_degenerate_groups(
    betas: Sequence[complex],
    *,
    relative_tolerance: float,
    absolute_tolerance: float,
) -> list[tuple[int, ...]]:
    parents = list(range(len(betas)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        root_first = find(first)
        root_second = find(second)
        if root_first != root_second:
            parents[root_second] = root_first

    for first in range(len(betas)):
        for second in range(first + 1, len(betas)):
            scale = max(abs(betas[first]), abs(betas[second]), 1.0e-12)
            if abs(betas[first] - betas[second]) <= max(
                absolute_tolerance, relative_tolerance * scale
            ):
                union(first, second)

    grouped: dict[int, list[int]] = {}
    for index in range(len(betas)):
        grouped.setdefault(find(index), []).append(index)
    return [tuple(indices) for indices in grouped.values()]


def _linear_combination(
    vectors: Sequence[PETSc.Vec], coefficients: np.ndarray
) -> PETSc.Vec:
    result = vectors[0].duplicate()
    result.set(0.0)
    for coefficient, vector in zip(coefficients, vectors):
        if abs(coefficient) > 0.0:
            result.axpy(complex(coefficient), vector)
    return result


def _identity_error_metrics(matrix: np.ndarray) -> tuple[float, float]:
    """Return induced-infinity and componentwise identity errors."""

    values = np.asarray(matrix, dtype=np.complex128)
    if values.ndim != 2 or values.shape[0] != values.shape[1]:
        raise ValueError("Biorthogonality matrix must be square.")
    difference = values - np.eye(values.shape[0], dtype=np.complex128)
    infinity_norm = float(np.linalg.norm(difference, ord=np.inf))
    max_entry = (
        float(np.max(np.abs(difference))) if difference.size else 0.0
    )
    return infinity_norm, max_entry


def _near_degenerate_partition_audit(
    betas: Sequence[complex],
    groups: Sequence[Sequence[int]],
    biorthogonality: np.ndarray,
    *,
    near_degenerate_tolerance: float,
    block_rotation_tolerance: float,
    directions: Sequence[str] | None = None,
) -> dict[str, object]:
    """Detect a physically coupled mode pair split across normalized blocks."""

    values = np.asarray(biorthogonality, dtype=np.complex128)
    if values.shape != (len(betas), len(betas)):
        raise ValueError("Biorthogonality and beta dimensions disagree.")
    identity_row_norm, identity_max_entry = _identity_error_metrics(values)
    group_members = [
        [int(index) for index in indices] for indices in groups
    ]
    group_id = np.full(len(betas), -1, dtype=np.int64)
    for identifier, indices in enumerate(groups):
        for index in indices:
            if group_id[int(index)] >= 0:
                raise ValueError("Near-degenerate groups overlap.")
            group_id[int(index)] = int(identifier)
    if np.any(group_id < 0):
        raise ValueError("Near-degenerate groups do not cover every mode.")

    cross_mask = group_id[:, None] != group_id[None, :]
    cross_values = np.where(cross_mask, np.abs(values), 0.0)
    if cross_values.size:
        flat_index = int(np.argmax(cross_values))
        row, column = (
            int(value)
            for value in np.unravel_index(flat_index, cross_values.shape)
        )
        maximum = float(cross_values[row, column])
    else:
        row = column = -1
        maximum = 0.0
    beta_distance = (
        _relative_beta_distance(betas[row], betas[column])
        if row >= 0 and column >= 0
        else 0.0
    )
    cross_overlap_pass = maximum <= float(block_rotation_tolerance)
    identity_row_norm_pass = (
        identity_row_norm <= float(block_rotation_tolerance)
    )
    passed = cross_overlap_pass and identity_row_norm_pass
    near_degenerate_candidate = bool(
        row >= 0
        and column >= 0
        and beta_distance <= 10.0 * float(near_degenerate_tolerance)
    )
    failure_status = (
        "near_degenerate_block_partition_split"
        if near_degenerate_candidate
        else "cross_block_biorthogonality_failure"
    )
    worst_directions = (
        [str(directions[row]), str(directions[column])]
        if directions is not None and row >= 0 and column >= 0
        else None
    )
    return {
        "status": (
            "near_degenerate_block_partition_pass"
            if passed
            else failure_status
        ),
        "pass": passed,
        "block_rotation_tolerance": float(block_rotation_tolerance),
        "biorthogonality_identity_row_norm": identity_row_norm,
        "biorthogonality_identity_max_entry": identity_max_entry,
        "biorthogonality_identity_row_norm_within_tolerance": (
            identity_row_norm_pass
        ),
        "max_cross_block_overlap": maximum,
        "max_cross_block_overlap_within_tolerance": cross_overlap_pass,
        "group_members": group_members,
        "worst_cross_block_indices": [row, column],
        "worst_cross_block_group_ids": (
            [int(group_id[row]), int(group_id[column])]
            if row >= 0 and column >= 0
            else [-1, -1]
        ),
        "worst_cross_block_group_members": (
            [
                group_members[int(group_id[row])],
                group_members[int(group_id[column])],
            ]
            if row >= 0 and column >= 0
            else [[], []]
        ),
        "worst_cross_block_relative_beta_distance": beta_distance,
        "near_degenerate_tolerance": float(near_degenerate_tolerance),
        "near_degenerate_candidate_factor": 10.0,
        "worst_cross_block_is_near_degenerate_candidate": (
            near_degenerate_candidate
        ),
        "worst_cross_block_betas": (
            [
                [float(betas[row].real), float(betas[row].imag)],
                [float(betas[column].real), float(betas[column].imag)],
            ]
            if row >= 0 and column >= 0
            else None
        ),
        "worst_cross_block_directions": worst_directions,
        "remediation": (
            None
            if passed
            else "DEFERRED_ARCHITECTURE_REQUIRED_joint_subspace_rotation"
        ),
    }


def _task036_scalar_stage4_partition_repair_candidate(
    cross_section: CrossSectionMesh,
    groups: Sequence[Sequence[int]],
    audit: dict[str, object],
    *,
    betas: Sequence[complex],
    directions: Sequence[str],
    biorthogonality: np.ndarray,
    near_degenerate_tolerance: float,
    block_rotation_tolerance: float,
    maximum_overlap_condition: float,
    maximum_union_size: int = 8,
) -> tuple[tuple[tuple[int, ...], ...] | None, dict[str, object]]:
    """Plan every bounded row-budget component before changing any vector."""

    group_members = [
        tuple(int(index) for index in indices) for indices in groups
    ]
    shape = getattr(cross_section.epsilon_r, "ufl_shape", None)
    scalar_material = shape is not None and tuple(shape) == ()
    provenance: dict[str, object] = {
        "policy": "task036_scalar_stage4_connected_component_joint_left_inverse",
        "maximum_attempts": 1,
        "maximum_union_size": int(maximum_union_size),
        "material_kind": str(cross_section.material_kind),
        "scalar_material": scalar_material,
        "eligible": False,
        "reason": None,
        "components": [],
        "component_count": 0,
    }

    def rejected(reason: str):
        provenance["reason"] = reason
        return None, provenance

    if cross_section.material_kind != "stage4_xy" or not scalar_material:
        return rejected("not_scalar_stage4_xy")
    if audit.get("pass") is True:
        return rejected("partition_already_passes")
    values = np.asarray(biorthogonality, dtype=np.complex128)
    if values.shape != (len(betas), len(betas)):
        return rejected("biorthogonality_shape_mismatch")
    if len(directions) != len(betas):
        return rejected("direction_count_mismatch")

    identity_difference = np.abs(
        values - np.eye(len(betas), dtype=np.complex128)
    )
    identity_row_errors = np.sum(identity_difference, axis=1)
    failing_rows = np.flatnonzero(
        identity_row_errors > float(block_rotation_tolerance)
    )
    group_id_by_mode = np.full(len(betas), -1, dtype=np.int64)
    for identifier, members in enumerate(group_members):
        for index in members:
            group_id_by_mode[index] = identifier
    if np.any(group_id_by_mode < 0):
        return rejected("group_members_do_not_cover_modes")
    failing_group_ids = {
        int(group_id_by_mode[index]) for index in failing_rows
    }
    if not failing_group_ids:
        return rejected("no_full_row_norm_failure_seed")
    noise_floor = (
        64.0
        * np.finfo(np.float64).eps
        * max(len(betas), 1)
        * max(1.0, float(np.linalg.norm(values, ord=np.inf)))
    )
    provenance.update(
        full_row_norm_failure_seed_group_ids=sorted(failing_group_ids),
        connected_edge_noise_floor=noise_floor,
        connected_edge_selection_semantics=(
            "minimum deterministic partner-group prefix whose row "
            "contribution exceeds the full identity-row-norm excess"
        ),
    )

    parents = list(range(len(group_members)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parents[second_root] = first_root

    selected_edges: dict[tuple[int, int], dict[str, object]] = {}
    row_failure_plans: list[dict[str, object]] = []
    unexplained_rows: list[dict[str, object]] = []
    for row in map(int, failing_rows):
        first = int(group_id_by_mode[row])
        first_members = group_members[first]
        candidates: list[tuple[float, int, float]] = []
        for second, second_members in enumerate(group_members):
            if second == first:
                continue
            component_directions = {
                str(directions[index])
                for index in (*first_members, *second_members)
            }
            same_direction = bool(
                len(component_directions) == 1
                and next(iter(component_directions))
                in {"forward", "backward"}
            )
            row_contribution = float(
                np.sum(np.abs(values[row, list(second_members)]))
            )
            beta_distance = min(
                _relative_beta_distance(betas[source], betas[column])
                for source in first_members
                for column in second_members
            )
            eligible = bool(
                same_direction
                and row_contribution > noise_floor
                and beta_distance
                <= 10.0 * float(near_degenerate_tolerance)
            )
            if eligible:
                candidates.append(
                    (row_contribution, int(second), beta_distance)
                )
        candidates.sort(key=lambda item: (-item[0], item[1]))
        required_reduction = float(
            identity_row_errors[row] - float(block_rotation_tolerance)
        )
        cumulative = 0.0
        selected_partner_ids: list[int] = []
        for row_contribution, second, beta_distance in candidates:
            selected_partner_ids.append(second)
            cumulative += row_contribution
            edge_key = tuple(sorted((first, second)))
            edge = selected_edges.setdefault(
                edge_key,
                {
                    "source_group_ids": list(edge_key),
                    "trigger_rows": [],
                    "maximum_group_row_contribution": 0.0,
                    "minimum_relative_beta_distance": beta_distance,
                },
            )
            edge["trigger_rows"].append(row)
            edge["maximum_group_row_contribution"] = max(
                float(edge["maximum_group_row_contribution"]),
                row_contribution,
            )
            edge["minimum_relative_beta_distance"] = min(
                float(edge["minimum_relative_beta_distance"]),
                beta_distance,
            )
            if cumulative > required_reduction:
                break
        row_plan = {
            "trigger_row": row,
            "source_group_id": first,
            "full_identity_row_error": float(identity_row_errors[row]),
            "required_reduction": required_reduction,
            "selected_partner_group_ids": selected_partner_ids,
            "cumulative_selected_contribution": cumulative,
            "noise_floor": noise_floor,
        }
        row_failure_plans.append(row_plan)
        if cumulative <= required_reduction:
            unexplained_rows.append(row_plan)
    provenance["row_failure_plans"] = row_failure_plans
    if unexplained_rows:
        provenance["unexplained_row_failures"] = unexplained_rows
        return rejected(
            "row_norm_failure_not_explained_by_near_cross_blocks"
        )

    edge_records = [
        selected_edges[key] for key in sorted(selected_edges)
    ]
    for first, second in sorted(selected_edges):
        union(first, second)

    connected_group_ids: dict[int, list[int]] = {}
    for identifier in range(len(group_members)):
        connected_group_ids.setdefault(find(identifier), []).append(
            identifier
        )
    candidate_group_ids = sorted(
        (
            tuple(sorted(identifiers))
            for identifiers in connected_group_ids.values()
            if len(identifiers) > 1
            and failing_group_ids.intersection(identifiers)
        ),
        key=lambda identifiers: min(
            min(group_members[identifier]) for identifier in identifiers
        ),
    )
    if not candidate_group_ids:
        return rejected("no_eligible_connected_components")

    component_records: list[dict[str, object]] = []
    merged_components: list[tuple[int, ...]] = []
    for identifiers in candidate_group_ids:
        merged = tuple(
            sorted(
                index
                for identifier in identifiers
                for index in group_members[identifier]
            )
        )
        record: dict[str, object] = {
            "source_group_ids": list(identifiers),
            "source_group_members": [
                list(group_members[identifier])
                for identifier in identifiers
            ],
            "merged_group_members": list(merged),
        }
        if len(merged) > int(maximum_union_size):
            provenance["components"] = [*component_records, record]
            return rejected("connected_component_exceeds_bounded_size")
        condition = float(
            np.linalg.cond(values[np.ix_(merged, merged)])
        )
        record["joint_overlap_condition"] = condition
        if (
            not np.isfinite(condition)
            or condition > float(maximum_overlap_condition)
        ):
            provenance["components"] = [*component_records, record]
            return rejected("connected_component_overlap_ill_conditioned")
        component_records.append(record)
        merged_components.append(merged)

    provenance["components"] = component_records
    provenance["component_count"] = len(component_records)
    provenance["edge_count"] = len(edge_records)
    provenance["edges"] = edge_records
    provenance.update(eligible=True, reason="eligible")
    return tuple(merged_components), provenance


def _joint_left_basis_inverse(
    left_reduced: list[PETSc.Vec],
    left_full: list[PETSc.Vec],
    indices: Sequence[int],
    raw_overlap: np.ndarray,
    *,
    maximum_overlap_condition: float,
) -> float:
    """Jointly normalize one bounded left block against fixed right modes."""

    selected = tuple(int(index) for index in indices)
    overlap = np.asarray(raw_overlap, dtype=np.complex128)
    if overlap.shape != (len(selected), len(selected)):
        raise ValueError("Joint left-basis overlap shape disagrees with its block.")
    condition = float(np.linalg.cond(overlap))
    if not np.isfinite(condition) or condition > maximum_overlap_condition:
        raise RuntimeError(
            "Task036 joint left-basis overlap is singular or ill-conditioned: "
            f"indices={selected}, condition={condition:.6e}."
        )
    try:
        transform = np.linalg.inv(overlap).conj().T
    except np.linalg.LinAlgError as error:
        raise RuntimeError(
            "Task036 joint left-basis overlap inversion failed: "
            f"indices={selected}, condition={condition:.6e}."
        ) from error
    old = (
        [left_reduced[index] for index in selected],
        [left_full[index] for index in selected],
    )
    new_reduced: list[PETSc.Vec] = []
    new_full: list[PETSc.Vec] = []
    try:
        new_reduced = [
            _linear_combination(old[0], transform[:, column])
            for column in range(len(selected))
        ]
        new_full = [
            _linear_combination(old[1], transform[:, column])
            for column in range(len(selected))
        ]
    except Exception:
        for vector in new_reduced + new_full:
            vector.destroy()
        raise
    for vector in old[0] + old[1]:
        vector.destroy()
    for local_index, global_index in enumerate(selected):
        left_reduced[global_index] = new_reduced[local_index]
        left_full[global_index] = new_full[local_index]
    return condition


def _scalar_stage4_reciprocal_full_transform(
    vector: PETSc.Vec,
    spaces: CrossSectionSpaces,
    *,
    left: bool,
) -> PETSc.Vec:
    """Apply ``S(Et, Ez)=(Et, -Ez)`` and the left-basis minus sign."""

    field = fem.Function(spaces.mixed)
    if int(vector.getSize()) != int(field.x.petsc_vec.getSize()):
        raise ValueError("Reciprocal source vector has the wrong full-space size.")
    vector.copy(field.x.petsc_vec)
    field.x.scatter_forward()
    field.x.array[spaces.longitudinal_to_mixed] *= -1.0
    if left:
        field.x.array[:] *= -1.0
    field.x.scatter_forward()
    transformed = field.x.petsc_vec.duplicate()
    field.x.petsc_vec.copy(transformed)
    return transformed


def _project_scalar_stage4_reciprocal(
    source: PETSc.Vec,
    spaces: CrossSectionSpaces,
    transform: PETSc.Mat,
    transform_h: PETSc.Mat,
    gram_diagonal: PETSc.Vec,
    *,
    left: bool,
    reconstruction_tolerance: float,
) -> tuple[PETSc.Vec, PETSc.Vec, float]:
    """Apply S/-S, project through ``C^H C``, and verify ``Cq``."""

    full = _scalar_stage4_reciprocal_full_transform(
        source, spaces, left=left
    )
    rhs = transform_h.createVecLeft()
    reduced = transform.createVecRight()
    reconstructed = transform.createVecLeft()
    difference = transform.createVecLeft()
    try:
        transform_h.mult(full, rhs)
        reduced.pointwiseDivide(rhs, gram_diagonal)
        transform.mult(reduced, reconstructed)
        full.copy(difference)
        difference.axpy(-1.0, reconstructed)
        relative_error = float(
            difference.norm(PETSc.NormType.NORM_2)
            / max(float(full.norm(PETSc.NormType.NORM_2)), 1.0e-30)
        )
        if (
            not np.isfinite(relative_error)
            or relative_error > float(reconstruction_tolerance)
        ):
            raise RuntimeError(
                "Scalar Stage-4 reciprocal vector is outside the Floquet "
                "constraint image: "
                f"relative_reconstruction={relative_error:.6e}, "
                f"limit={float(reconstruction_tolerance):.6e}."
            )
        return reduced, reconstructed, relative_error
    except Exception:
        reduced.destroy()
        reconstructed.destroy()
        raise
    finally:
        full.destroy()
        rhs.destroy()
        difference.destroy()


def build_scalar_stage4_reciprocal_negative_basis(
    cfg: SimulationConfig3D,
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    operators: QuadraticBetaOperators,
    positive: BiorthogonalModeBasis,
    *,
    reconstruction_tolerance: float = 1.0e-12,
    maximum_right_polynomial_relative_residual: float = 1.0e-8,
    maximum_left_polynomial_relative_residual: float = 1.0e-8,
    near_degenerate_tolerance: float = 1.0e-6,
    identity_tolerance: float = 1.0e-6,
    maximum_left_pair_relative_error: float = 1.0e-7,
    relative_flux_tolerance: float = 1.0e-8,
    absolute_flux_tolerance: float = 1.0e-12,
    beta_imag_tolerance: float = 1.0e-10,
    poynting_evaluator: PoyntingFluxEvaluator | None = None,
) -> BiorthogonalModeBasis:
    """Build the opt-in reciprocal ``-beta`` basis for scalar ``stage4_xy``.

    Every physical and algebraic Gate is recomputed.  An independently solved
    negative QEP remains a separate audit and is not represented by this
    analytic construction.
    """

    scalar_material = tuple(
        getattr(cross_section.epsilon_r, "ufl_shape", (None,))
    ) == ()
    if cross_section.material_kind != "stage4_xy" or not scalar_material:
        raise ValueError(
            "Analytic reciprocal construction is restricted to scalar stage4_xy."
        )
    if not positive.modes:
        raise ValueError("A nonempty positive basis is required.")
    if any(
        mode.direction != "forward" or not mode.passive_branch_valid
        for mode in positive.modes
    ):
        raise RuntimeError(
            "Analytic reciprocal construction requires a passive forward basis."
        )
    limits = (
        reconstruction_tolerance,
        maximum_right_polynomial_relative_residual,
        maximum_left_polynomial_relative_residual,
        near_degenerate_tolerance,
        identity_tolerance,
        maximum_left_pair_relative_error,
    )
    if any(not np.isfinite(value) or value <= 0.0 for value in limits):
        raise ValueError("Analytic reciprocal Gate limits must be positive.")
    if identity_tolerance < near_degenerate_tolerance:
        raise ValueError(
            "identity_tolerance cannot be smaller than near_degenerate_tolerance."
        )

    transform = operators.transform.matrix
    transform_h = PETSc.Mat()
    transform.hermitianTranspose(transform_h)
    gram = transform_h.matMult(transform)
    gram_diagonal = gram.getDiagonal()
    adjoints = (
        _adjoint_matrix(operators.K0),
        _adjoint_matrix(operators.K1),
        _adjoint_matrix(operators.K2),
    )
    right_modes: list[QuadraticBetaMode] = []
    left_reduced: list[PETSc.Vec] = []
    left_full: list[PETSc.Vec] = []
    right_reconstruction: list[float] = []
    left_reconstruction: list[float] = []
    left_residuals: list[float] = []
    try:
        for source in positive.modes:
            reduced = full = left_q = left_cq = None
            try:
                reduced, full, right_error = (
                    _project_scalar_stage4_reciprocal(
                        source.right.right_full,
                        spaces,
                        transform,
                        transform_h,
                        gram_diagonal,
                        left=False,
                        reconstruction_tolerance=reconstruction_tolerance,
                    )
                )
                left_q, left_cq, left_error = (
                    _project_scalar_stage4_reciprocal(
                        source.left_full,
                        spaces,
                        transform,
                        transform_h,
                        gram_diagonal,
                        left=True,
                        reconstruction_tolerance=reconstruction_tolerance,
                    )
                )
                beta = -complex(source.beta)
                right_residual = quadratic_beta_polynomial_relative_residual(
                    operators, beta, reduced
                )
                left_residual = _left_relative_residual(
                    adjoints, beta, left_q
                )
                if (
                    not np.isfinite(right_residual)
                    or right_residual
                    > maximum_right_polynomial_relative_residual
                ):
                    raise RuntimeError(
                        "Analytic reciprocal right polynomial residual failed: "
                        f"{right_residual:.6e}."
                    )
                if (
                    not np.isfinite(left_residual)
                    or left_residual
                    > maximum_left_polynomial_relative_residual
                ):
                    raise RuntimeError(
                        "Analytic reciprocal left polynomial residual failed: "
                        f"{left_residual:.6e}."
                    )
                mass_norm = _electric_mass_overlap(
                    operators.electric_mass, reduced, reduced
                ).real
                right_modes.append(
                    QuadraticBetaMode(
                        beta=beta,
                        right_reduced=reduced,
                        right_full=full,
                        polynomial_relative_residual=right_residual,
                        slepc_relative_error=source.right.slepc_relative_error,
                        normalization_kind=(
                            "analytic_scalar_stage4_reciprocal"
                        ),
                        normalization_factor=(
                            source.right.normalization_factor
                        ),
                        electric_l2_norm_after=float(
                            np.sqrt(max(mass_norm, 0.0))
                        ),
                        ownership=source.right.ownership,
                    )
                )
                left_reduced.append(left_q)
                left_full.append(left_cq)
                right_reconstruction.append(right_error)
                left_reconstruction.append(left_error)
                left_residuals.append(left_residual)
                reduced = full = left_q = left_cq = None
            finally:
                for vector in (reduced, full, left_q, left_cq):
                    if vector is not None:
                        vector.destroy()

        betas = [mode.beta for mode in right_modes]
        left_betas = [
            np.conj(-complex(source.left_adjoint_beta))
            for source in positive.modes
        ]
        biorthogonality = _qep_overlap_matrix(
            operators,
            left_betas,
            betas,
            left_reduced,
            [mode.right_reduced for mode in right_modes],
        )
        max_identity_error, max_entry_identity_error = (
            _identity_error_metrics(biorthogonality)
        )
        flux_evaluator = poynting_evaluator or PoyntingFluxEvaluator(
            cfg, cross_section, spaces
        )
        fluxes = [
            flux_evaluator.evaluate(mode.right_full, mode.beta)
            for mode in right_modes
        ]
        flux_tolerance = max(
            float(absolute_flux_tolerance),
            float(relative_flux_tolerance)
            * max((abs(value) for value in fluxes), default=0.0),
        )
        classifications = [
            classify_mode_branch(
                mode.beta, flux, flux_tolerance, beta_imag_tolerance
            )
            for mode, flux in zip(right_modes, fluxes)
        ]
        if any(
            direction != "backward" or not passive
            for _kind, direction, _basis, passive in classifications
        ):
            raise RuntimeError(
                "Analytic reciprocal Poynting/passivity classification failed."
            )
        group_indices = [group.indices for group in positive.groups]
        partition_audit = _near_degenerate_partition_audit(
            betas,
            group_indices,
            biorthogonality,
            near_degenerate_tolerance=near_degenerate_tolerance,
            block_rotation_tolerance=identity_tolerance,
            directions=[classification[1] for classification in classifications],
        )
        if (
            max_identity_error > identity_tolerance
            or not partition_audit["pass"]
        ):
            raise NearDegenerateBlockPartitionSplitError(partition_audit)
        left_pair_errors = tuple(
            _relative_beta_distance(
                np.conj(-complex(source.left_adjoint_beta)), beta
            )
            for source, beta in zip(positive.modes, betas)
        )
        _require_admissible_left_pairs(
            left_pair_errors,
            maximum_relative_error=maximum_left_pair_relative_error,
        )
        groups = tuple(
            replace(
                source_group,
                beta_center=-complex(source_group.beta_center),
                overlap_condition=float(
                    np.linalg.cond(biorthogonality[np.ix_(indices, indices)])
                ),
                normalization_method="analytic_scalar_stage4_reciprocal",
                post_normalization_identity_error=float(
                    np.linalg.norm(
                        biorthogonality[np.ix_(indices, indices)]
                        - np.eye(len(indices)),
                        ord=np.inf,
                    )
                ),
            )
            for source_group, indices in zip(positive.groups, group_indices)
        )
        classified = [
            ClassifiedBiorthogonalMode(
                beta=right.beta,
                right=right,
                left_reduced=left_reduced[index],
                left_full=left_full[index],
                left_adjoint_beta=-complex(source.left_adjoint_beta),
                left_polynomial_relative_residual=left_residuals[index],
                poynting_z_before_normalization=fluxes[index],
                poynting_z_after_normalization=fluxes[index],
                flux_tolerance=flux_tolerance,
                kind=classifications[index][0],
                direction=classifications[index][1],
                classification_basis=classifications[index][2],
                passive_branch_valid=classifications[index][3],
                right_scale=1.0,
                qprime_overlap_after=complex(biorthogonality[index, index]),
                left_ownership=source.left_ownership,
            )
            for index, (source, right) in enumerate(
                zip(positive.modes, right_modes)
            )
        ]
        audit = {
            "status": "pass",
            "source_basis_origin": positive.basis_origin,
            "source_mode_count": len(positive.modes),
            "right_transform": "S(Et,Ez)=(Et,-Ez)",
            "left_transform": "-S(Et,Ez)=(-Et,+Ez)",
            "constraint_projection": "diagonal_normal_equations",
            "constraint_reconstruction_tolerance": reconstruction_tolerance,
            "right_constraint_reconstruction_relative_errors": (
                right_reconstruction
            ),
            "left_constraint_reconstruction_relative_errors": left_reconstruction,
            "right_polynomial_relative_residuals": [
                mode.polynomial_relative_residual for mode in right_modes
            ],
            "left_polynomial_relative_residuals": left_residuals,
            "qprime_identity_row_norm": max_identity_error,
            "qprime_identity_max_entry": max_entry_identity_error,
            "poynting_z": fluxes,
            "directions": [classification[1] for classification in classifications],
            "passive_branches_valid": all(
                classification[3] for classification in classifications
            ),
            "all_residual_flux_qprime_recomputed": True,
            "negative_independent_qep_solve_performed": False,
            "adjoint_solver_report_provenance": (
                "source_positive_basis_only; independent negative QEP audit "
                "remains external"
            ),
        }
        return BiorthogonalModeBasis(
            modes=classified,
            groups=groups,
            biorthogonality_matrix=biorthogonality,
            max_identity_error=max_identity_error,
            max_entry_identity_error=max_entry_identity_error,
            adjoint_solver_report=replace(
                positive.adjoint_solver_report,
                target=-complex(positive.adjoint_solver_report.target),
            ),
            left_pair_relative_errors=left_pair_errors,
            near_degenerate_partition_audit=partition_audit,
            basis_origin="analytic_scalar_stage4_reciprocal",
            basis_construction_audit=audit,
        )
    except Exception:
        for mode in right_modes:
            mode.destroy()
        for vector in left_reduced + left_full:
            vector.destroy()
        raise
    finally:
        for matrix in adjoints:
            matrix.destroy()
        gram_diagonal.destroy()
        gram.destroy()
        transform_h.destroy()


def classify_mode_branch(
    beta: complex,
    poynting_z: float,
    flux_tolerance: float,
    beta_imag_tolerance: float,
) -> tuple[ModeKind, ModeDirection, str, bool]:
    if abs(poynting_z) > flux_tolerance:
        direction: ModeDirection = "forward" if poynting_z > 0.0 else "backward"
        kind: ModeKind = (
            "propagating"
            if abs(beta.imag) <= beta_imag_tolerance
            else "lossy_propagating"
        )
        direction_sign = 1.0 if direction == "forward" else -1.0
        passive = (
            abs(beta.imag) <= beta_imag_tolerance
            or direction_sign * beta.imag > 0.0
        )
        return kind, direction, "poynting_flux", passive

    if beta.imag > beta_imag_tolerance:
        return "evanescent", "forward", "positive_imag_beta_decay", True
    if beta.imag < -beta_imag_tolerance:
        return "evanescent", "backward", "negative_imag_beta_decay", True
    return (
        "cutoff_or_near_zero_flux",
        "ambiguous",
        "near_zero_flux_and_beta_imag",
        False,
    )


def select_passive_direction_modes(
    right_modes: list[QuadraticBetaMode],
    *,
    desired_direction: ModeDirection,
    requested_modes: int,
    poynting_evaluator: PoyntingFluxEvaluator,
    relative_flux_tolerance: float = 1.0e-8,
    absolute_flux_tolerance: float = 1.0e-12,
    beta_imag_tolerance: float = 1.0e-10,
    maximum_abs_beta: float | None = None,
) -> tuple[list[QuadraticBetaMode], DirectionalModeSelectionReport]:
    """Filter a target-slice candidate pool before biorthogonalization.

    A large shift-invert target slice can contain the reciprocal branch even
    when its target beta is positive (and vice versa).  This filter keeps only
    the requested passive direction and destroys every rejected distributed
    candidate.  Candidate ordering from the QEP target is preserved.
    """

    if desired_direction not in {"forward", "backward"}:
        raise ValueError("Directional selection requires forward or backward.")
    if requested_modes < 1:
        raise ValueError("requested_modes must be positive.")
    if not right_modes:
        raise ValueError("At least one directional candidate is required.")
    if maximum_abs_beta is not None and (
        not np.isfinite(maximum_abs_beta) or maximum_abs_beta <= 0.0
    ):
        raise ValueError("maximum_abs_beta must be finite and positive when supplied.")
    finite_indices = [
        index
        for index, mode in enumerate(right_modes)
        if np.isfinite(mode.beta.real)
        and np.isfinite(mode.beta.imag)
        and (maximum_abs_beta is None or abs(mode.beta) <= maximum_abs_beta)
    ]
    finite_ids = set(finite_indices)
    rejected_indices = [
        index for index in range(len(right_modes)) if index not in finite_ids
    ]
    finite_modes = [right_modes[index] for index in finite_indices]
    fluxes = [
        poynting_evaluator.evaluate(mode.right_full, mode.beta)
        for mode in finite_modes
    ]
    flux_tolerance = max(
        float(absolute_flux_tolerance),
        float(relative_flux_tolerance)
        * max((abs(value) for value in fluxes), default=0.0),
    )
    classifications = [
        classify_mode_branch(
            mode.beta,
            flux,
            flux_tolerance,
            beta_imag_tolerance,
        )
        for mode, flux in zip(finite_modes, fluxes)
    ]
    eligible = [
        finite_indices[index]
        for index, (_kind, direction, _basis, passive) in enumerate(classifications)
        if direction == desired_direction and passive
    ]
    selected_indices = tuple(eligible[:requested_modes])
    selected_ids = set(selected_indices)
    selected = [right_modes[index] for index in selected_indices]
    first_rejected_beta = (
        None
        if not rejected_indices
        else complex(right_modes[rejected_indices[0]].beta)
    )
    for index, mode in enumerate(right_modes):
        if index not in selected_ids:
            mode.destroy()
    counts: dict[str, int] = {"forward": 0, "backward": 0, "ambiguous": 0}
    for _kind, direction, _basis, _passive in classifications:
        counts[direction] = counts.get(direction, 0) + 1
    report = DirectionalModeSelectionReport(
        requested_modes=int(requested_modes),
        candidate_modes=len(right_modes),
        selected_modes=len(selected),
        desired_direction=desired_direction,
        direction_counts=counts,
        passive_candidate_count=sum(1 for *_prefix, passive in classifications if passive),
        selected_candidate_indices=selected_indices,
        flux_tolerance=flux_tolerance,
        finite_candidate_count=len(finite_modes),
        numerically_infinite_candidate_count=len(rejected_indices),
        abs_beta_cutoff=(
            None if maximum_abs_beta is None else float(maximum_abs_beta)
        ),
        first_rejected_numerical_infinity_beta=(
            first_rejected_beta
        ),
    )
    return selected, report


def build_biorthogonal_mode_basis(
    cfg: SimulationConfig3D,
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    operators: QuadraticBetaOperators,
    right_modes: list[QuadraticBetaMode],
    *,
    adjoint_target: complex,
    requested_left_modes: int | None = None,
    relative_flux_tolerance: float = 1.0e-8,
    absolute_flux_tolerance: float = 1.0e-12,
    beta_imag_tolerance: float = 1.0e-10,
    near_degenerate_tolerance: float = 1.0e-6,
    block_rotation_tolerance: float = 1.0e-6,
    maximum_overlap_condition: float = 1.0e12,
    maximum_left_pair_relative_error: float = 1.0e-7,
    task036_scalar_stage4_partition_repair: bool = False,
    poynting_evaluator: PoyntingFluxEvaluator | None = None,
    log=None,
) -> BiorthogonalModeBasis:
    """Add Poynting classification and adjoint-QEP biorthogonality.

    Ownership of ``right_modes`` transfers to the returned basis. Full FE
    vectors remain distributed; only mode-count-sized dense overlap matrices
    are replicated.
    """

    if not right_modes:
        raise ValueError("At least one right mode is required.")
    if (
        not np.isfinite(near_degenerate_tolerance)
        or near_degenerate_tolerance <= 0.0
    ):
        raise ValueError("Near-degenerate tolerance must be finite and positive.")
    if (
        not np.isfinite(block_rotation_tolerance)
        or block_rotation_tolerance < near_degenerate_tolerance
    ):
        raise ValueError(
            "Block-rotation tolerance must be finite and no smaller than the "
            "near-degenerate tolerance so every identified group is rotated."
        )
    requested = max(
        len(right_modes),
        int(requested_left_modes or len(right_modes)),
    )
    adjoints = (
        _adjoint_matrix(operators.K0),
        _adjoint_matrix(operators.K1),
        _adjoint_matrix(operators.K2),
    )
    adjoint_operators = QuadraticBetaOperators(
        K0=adjoints[0],
        K1=adjoints[1],
        K2=adjoints[2],
        electric_mass=operators.electric_mass,
        transform=operators.transform,
        constraints=operators.constraints,
        full_shape=operators.full_shape,
        reduced_shape=operators.reduced_shape,
        scalar_dtype=operators.scalar_dtype,
        field_degree=operators.field_degree,
        geometry_degree=operators.geometry_degree,
        coefficient_degree=operators.coefficient_degree,
        quadrature_degree=operators.quadrature_degree,
        quadrature_policy=operators.quadrature_policy,
    )
    left_candidates: list[QuadraticBetaMode] = []
    try:
        left_candidates, adjoint_report = solve_quadratic_beta_modes(
            adjoint_operators,
            target=complex(adjoint_target),
            requested_modes=requested,
        )
        if log is not None:
            log("Task32 mode basis: adjoint QEP solve returned")
        if len(left_candidates) < len(right_modes):
            raise RuntimeError(
                "Adjoint QEP returned fewer left modes than the right-mode basis."
            )

        candidate_left_betas = [
            np.conj(complex(mode.beta)) for mode in left_candidates
        ]
        pairing_overlaps = _qep_overlap_matrix(
            operators,
            candidate_left_betas,
            [complex(mode.beta) for mode in right_modes],
            [mode.right_reduced for mode in left_candidates],
            [mode.right_reduced for mode in right_modes],
        )
        pairing_cost = np.empty(
            (len(right_modes), len(left_candidates)), dtype=np.float64
        )
        for row, right in enumerate(right_modes):
            for column, left in enumerate(left_candidates):
                beta_error = _relative_beta_distance(
                    np.conj(left.beta), right.beta
                )
                overlap = abs(pairing_overlaps[column, row])
                pairing_cost[row, column] = beta_error - 1.0e-8 * np.log1p(
                    overlap
                )
        rows, columns = linear_sum_assignment(pairing_cost)
        selected_by_right = {
            int(row): left_candidates[int(column)]
            for row, column in zip(rows, columns)
        }
        if set(selected_by_right) != set(range(len(right_modes))):
            raise RuntimeError("Left/right assignment did not cover every right mode.")
        selected_left = [selected_by_right[index] for index in range(len(right_modes))]
        selected_ids = {id(mode) for mode in selected_left}
        for candidate in left_candidates:
            if id(candidate) not in selected_ids:
                candidate.destroy()
        left_candidates = selected_left
        if log is not None:
            log("Task32 mode basis: left/right assignment complete")

        left_pair_errors = tuple(
            _relative_beta_distance(np.conj(left.beta), right.beta)
            for right, left in zip(right_modes, left_candidates)
        )
        _require_admissible_left_pairs(
            left_pair_errors,
            maximum_relative_error=maximum_left_pair_relative_error,
        )

        flux_evaluator = poynting_evaluator or PoyntingFluxEvaluator(
            cfg, cross_section, spaces
        )
        flux_before = [
            flux_evaluator.evaluate(mode.right_full, mode.beta)
            for mode in right_modes
        ]
        if log is not None:
            log("Task32 mode basis: Poynting classification inputs complete")
        flux_tolerance = max(
            float(absolute_flux_tolerance),
            float(relative_flux_tolerance)
            * max((abs(value) for value in flux_before), default=0.0),
        )
        classifications = [
            classify_mode_branch(
                mode.beta,
                flux,
                flux_tolerance,
                beta_imag_tolerance,
            )
            for mode, flux in zip(right_modes, flux_before)
        ]
        right_scales: list[float] = []
        for mode, flux, (_, direction, _, _) in zip(
            right_modes, flux_before, classifications
        ):
            if direction in {"forward", "backward"} and abs(flux) > flux_tolerance:
                scale = float(1.0 / np.sqrt(abs(flux)))
                mode.right_reduced.scale(scale)
                mode.right_full.scale(scale)
                mode.electric_l2_norm_after *= abs(scale)
                mode.normalization_factor /= scale
                mode.normalization_kind = "phase3_unit_abs_poynting"
            else:
                scale = 1.0
                mode.normalization_kind = "phase3_electric_L2_near_zero_flux"
            right_scales.append(scale)
        if log is not None:
            log("Task32 mode basis: right-mode flux normalization complete")

        betas = [complex(mode.beta) for mode in right_modes]
        left_betas = [np.conj(complex(mode.beta)) for mode in left_candidates]
        left_reduced = [mode.right_reduced for mode in left_candidates]
        left_full = [mode.right_full for mode in left_candidates]
        group_indices = _near_degenerate_groups(
            betas,
            relative_tolerance=near_degenerate_tolerance,
            absolute_tolerance=1.0e-12,
        )
        raw_biorthogonality = _qep_overlap_matrix(
            operators,
            left_betas,
            betas,
            left_reduced,
            [mode.right_reduced for mode in right_modes],
        )
        group_payload: list[
            tuple[tuple[int, ...], complex, float, float, str]
        ] = []
        for indices in group_indices:
            group_betas = np.asarray([betas[index] for index in indices])
            center = complex(np.mean(group_betas))
            spread = max(
                (_relative_beta_distance(beta, center) for beta in group_betas),
                default=0.0,
            )
            raw_overlap = raw_biorthogonality[np.ix_(indices, indices)]
            condition = float(np.linalg.cond(raw_overlap))
            if not np.isfinite(condition) or condition > maximum_overlap_condition:
                raise RuntimeError(
                    "Near-degenerate left/right overlap is singular or ill-conditioned: "
                    f"indices={indices}, condition={condition:.6e}."
                )

            if len(indices) > 1:
                transform = np.linalg.inv(raw_overlap).conj().T
                old_reduced = [left_reduced[index] for index in indices]
                old_full = [left_full[index] for index in indices]
                new_reduced = [
                    _linear_combination(old_reduced, transform[:, column])
                    for column in range(len(indices))
                ]
                new_full = [
                    _linear_combination(old_full, transform[:, column])
                    for column in range(len(indices))
                ]
                for vector in old_reduced + old_full:
                    vector.destroy()
                for local_index, global_index in enumerate(indices):
                    left_reduced[global_index] = new_reduced[local_index]
                    left_full[global_index] = new_full[local_index]
                    left_candidates[global_index].right_reduced = (
                        new_reduced[local_index]
                    )
                    left_candidates[global_index].right_full = (
                        new_full[local_index]
                    )
                method = "near_degenerate_block_inverse"
            else:
                for local_index, global_index in enumerate(indices):
                    diagonal = raw_overlap[local_index, local_index]
                    if abs(diagonal) <= 1.0e-14:
                        raise RuntimeError(
                            "Q'(beta) left/right overlap is numerically zero."
                        )
                    left_scale = 1.0 / np.conj(diagonal)
                    left_reduced[global_index].scale(left_scale)
                    left_full[global_index].scale(left_scale)
                method = "diagonal_qprime"
            group_payload.append((indices, center, spread, condition, method))
        if log is not None:
            log("Task32 mode basis: biorthogonal group normalization complete")

        biorthogonality = _qep_overlap_matrix(
            operators,
            left_betas,
            betas,
            left_reduced,
            [mode.right_reduced for mode in right_modes],
        )
        directions = [
            str(classification[1]) for classification in classifications
        ]
        partition_audit = _near_degenerate_partition_audit(
            betas,
            group_indices,
            biorthogonality,
            near_degenerate_tolerance=near_degenerate_tolerance,
            block_rotation_tolerance=block_rotation_tolerance,
            directions=directions,
        )
        initial_partition_audit = dict(partition_audit)
        repair_provenance: dict[str, object] = {
            "requested": bool(task036_scalar_stage4_partition_repair),
            "applied": False,
            "initial_status": str(partition_audit["status"]),
            "initial_biorthogonality_identity_row_norm": float(
                partition_audit["biorthogonality_identity_row_norm"]
            ),
            "initial_max_cross_block_overlap": float(
                partition_audit["max_cross_block_overlap"]
            ),
        }
        if (
            task036_scalar_stage4_partition_repair
            and not partition_audit["pass"]
        ):
            merged_components, eligibility = (
                _task036_scalar_stage4_partition_repair_candidate(
                    cross_section,
                    group_indices,
                    partition_audit,
                    betas=betas,
                    directions=directions,
                    biorthogonality=biorthogonality,
                    near_degenerate_tolerance=near_degenerate_tolerance,
                    block_rotation_tolerance=block_rotation_tolerance,
                    maximum_overlap_condition=maximum_overlap_condition,
                )
            )
            repair_provenance.update(eligibility)
            if merged_components is not None:
                existing_payload = {
                    payload[0]: payload for payload in group_payload
                }
                removed: set[int] = set()
                merged_payload: dict[
                    tuple[int, ...],
                    tuple[tuple[int, ...], complex, float, float, str],
                ] = {}
                joint_conditions: list[float] = []
                component_records = eligibility["components"]
                for merged_indices, component_record in zip(
                    merged_components,
                    component_records,
                    strict=True,
                ):
                    condition = _joint_left_basis_inverse(
                        left_reduced,
                        left_full,
                        merged_indices,
                        biorthogonality[
                            np.ix_(merged_indices, merged_indices)
                        ],
                        maximum_overlap_condition=(
                            maximum_overlap_condition
                        ),
                    )
                    joint_conditions.append(condition)
                    removed.update(
                        map(int, component_record["source_group_ids"])
                    )
                    for index in merged_indices:
                        left_candidates[index].right_reduced = (
                            left_reduced[index]
                        )
                        left_candidates[index].right_full = left_full[index]
                    group_betas = [
                        betas[index] for index in merged_indices
                    ]
                    center = complex(np.mean(group_betas))
                    spread = max(
                        (
                            _relative_beta_distance(beta, center)
                            for beta in group_betas
                        ),
                        default=0.0,
                    )
                    merged_payload[merged_indices] = (
                        merged_indices,
                        center,
                        spread,
                        condition,
                        "task036_connected_component_joint_inverse",
                    )
                group_indices = [
                    indices
                    for index, indices in enumerate(group_indices)
                    if index not in removed
                ] + list(merged_components)
                group_indices.sort(key=min)
                group_payload = []
                for indices in group_indices:
                    if indices not in merged_payload:
                        group_payload.append(existing_payload[indices])
                        continue
                    group_payload.append(merged_payload[indices])
                biorthogonality = _qep_overlap_matrix(
                    operators,
                    left_betas,
                    betas,
                    left_reduced,
                    [mode.right_reduced for mode in right_modes],
                )
                partition_audit = _near_degenerate_partition_audit(
                    betas,
                    group_indices,
                    biorthogonality,
                    near_degenerate_tolerance=near_degenerate_tolerance,
                    block_rotation_tolerance=block_rotation_tolerance,
                    directions=directions,
                )
                repair_provenance.update(
                    applied=True,
                    joint_overlap_conditions=joint_conditions,
                    connected_component_count=len(merged_components),
                    right_modes_changed=False,
                    beta_values_changed=False,
                    left_basis_joint_inverse_only=True,
                )
        repair_provenance.update(
            final_status=str(partition_audit["status"]),
            final_pass=bool(partition_audit["pass"]),
            final_biorthogonality_identity_row_norm=float(
                partition_audit["biorthogonality_identity_row_norm"]
            ),
            final_max_cross_block_overlap=float(
                partition_audit["max_cross_block_overlap"]
            ),
        )
        partition_audit["repair"] = repair_provenance
        partition_audit["initial_audit"] = initial_partition_audit
        if not partition_audit["pass"]:
            raise NearDegenerateBlockPartitionSplitError(partition_audit)
        groups: list[NearDegenerateGroup] = []
        for indices, center, spread, condition, method in group_payload:
            block = biorthogonality[np.ix_(indices, indices)]
            groups.append(
                NearDegenerateGroup(
                    indices=indices,
                    beta_center=center,
                    max_relative_beta_spread=spread,
                    overlap_condition=condition,
                    normalization_method=method,
                    post_normalization_identity_error=float(
                        np.linalg.norm(block - np.eye(len(indices)), ord=np.inf)
                    ),
                )
            )

        classified: list[ClassifiedBiorthogonalMode] = []
        for index, (
            right,
            left_candidate,
            poynting_before,
            classification,
        ) in enumerate(
            zip(right_modes, left_candidates, flux_before, classifications)
        ):
            kind, direction, classification_basis, passive = classification
            poynting_after = flux_evaluator.evaluate(right.right_full, right.beta)
            classified.append(
                ClassifiedBiorthogonalMode(
                    beta=complex(right.beta),
                    right=right,
                    left_reduced=left_reduced[index],
                    left_full=left_full[index],
                    left_adjoint_beta=complex(left_candidate.beta),
                    left_polynomial_relative_residual=_left_relative_residual(
                        adjoints, right.beta, left_reduced[index]
                    ),
                    poynting_z_before_normalization=poynting_before,
                    poynting_z_after_normalization=poynting_after,
                    flux_tolerance=flux_tolerance,
                    kind=kind,
                    direction=direction,
                    classification_basis=classification_basis,
                    passive_branch_valid=passive,
                    right_scale=right_scales[index],
                    qprime_overlap_after=complex(biorthogonality[index, index]),
                    left_ownership=left_candidate.ownership,
                )
            )
        if log is not None:
            log("Task32 mode basis: classified mode records complete")

        max_identity_error, max_entry_identity_error = (
            _identity_error_metrics(biorthogonality)
        )
        return BiorthogonalModeBasis(
            modes=classified,
            groups=tuple(groups),
            biorthogonality_matrix=biorthogonality,
            max_identity_error=max_identity_error,
            max_entry_identity_error=max_entry_identity_error,
            adjoint_solver_report=adjoint_report,
            left_pair_relative_errors=left_pair_errors,
            near_degenerate_partition_audit=partition_audit,
        )
    except Exception:
        for mode in right_modes:
            mode.destroy()
        for candidate in left_candidates:
            try:
                candidate.destroy()
            except Exception:
                pass
        raise
    finally:
        for matrix in adjoints:
            matrix.destroy()


def pair_reciprocal_mode_bases(
    operators: QuadraticBetaOperators,
    positive: BiorthogonalModeBasis,
    negative: BiorthogonalModeBasis,
) -> tuple[ReciprocalModePair, ...]:
    if not positive.modes or not negative.modes:
        return ()
    cost = np.empty((len(positive.modes), len(negative.modes)), dtype=np.float64)
    overlaps = np.empty_like(cost)
    for row, plus in enumerate(positive.modes):
        for column, minus in enumerate(negative.modes):
            overlap = _normalized_mass_overlap(
                operators.electric_mass,
                plus.right.right_reduced,
                minus.right.right_reduced,
            )
            overlaps[row, column] = overlap
            reciprocal_error = float(
                abs(plus.beta + minus.beta)
                / max(abs(plus.beta), abs(minus.beta), 1.0e-12)
            )
            cost[row, column] = reciprocal_error + 1.0e-6 * (1.0 - overlap)
    rows, columns = linear_sum_assignment(cost)
    return tuple(
        ReciprocalModePair(
            positive_index=int(row),
            negative_index=int(column),
            relative_beta_error=float(
                abs(positive.modes[int(row)].beta + negative.modes[int(column)].beta)
                / max(
                    abs(positive.modes[int(row)].beta),
                    abs(negative.modes[int(column)].beta),
                    1.0e-12,
                )
            ),
            electric_mass_overlap=float(overlaps[int(row), int(column)]),
            opposite_direction=(
                positive.modes[int(row)].direction
                != negative.modes[int(column)].direction
            ),
            passive_branches_valid=(
                positive.modes[int(row)].passive_branch_valid
                and negative.modes[int(column)].passive_branch_valid
            ),
        )
        for row, column in zip(rows, columns)
    )


def _inverse_square_root_hermitian(matrix: np.ndarray) -> np.ndarray:
    hermitian = 0.5 * (matrix + matrix.conj().T)
    values, vectors = np.linalg.eigh(hermitian)
    if np.min(values) <= 1.0e-14 * max(np.max(values), 1.0):
        raise RuntimeError("Mode subspace Gram matrix is singular.")
    return (vectors * (1.0 / np.sqrt(values))) @ vectors.conj().T


def _subspace_report(
    mass: PETSc.Mat,
    previous: BiorthogonalModeBasis,
    current: BiorthogonalModeBasis,
    previous_indices: tuple[int, ...],
    current_indices: tuple[int, ...],
) -> SubspaceTrackingReport:
    previous_vectors = [
        previous.modes[index].right.right_reduced for index in previous_indices
    ]
    current_vectors = [
        current.modes[index].right.right_reduced for index in current_indices
    ]
    gram_previous = np.asarray(
        [
            [_electric_mass_overlap(mass, first, second) for second in previous_vectors]
            for first in previous_vectors
        ],
        dtype=np.complex128,
    )
    gram_current = np.asarray(
        [
            [_electric_mass_overlap(mass, first, second) for second in current_vectors]
            for first in current_vectors
        ],
        dtype=np.complex128,
    )
    cross = np.asarray(
        [
            [_electric_mass_overlap(mass, first, second) for second in current_vectors]
            for first in previous_vectors
        ],
        dtype=np.complex128,
    )
    whitened = (
        _inverse_square_root_hermitian(gram_previous)
        @ cross
        @ _inverse_square_root_hermitian(gram_current)
    )
    singular_values = np.clip(
        np.linalg.svd(whitened, compute_uv=False), 0.0, 1.0
    )
    angles = np.arccos(singular_values)
    return SubspaceTrackingReport(
        previous_indices=previous_indices,
        current_indices=current_indices,
        singular_values=tuple(float(value) for value in singular_values),
        max_principal_angle_rad=float(np.max(angles, initial=0.0)),
    )


def track_mode_bases(
    operators: QuadraticBetaOperators,
    previous: BiorthogonalModeBasis,
    current: BiorthogonalModeBasis,
) -> ModeTrackingReport:
    """Track modes by left/right overlap and compare degenerate subspaces."""

    if operators.reduced_shape[0] == 0:
        raise ValueError("Cannot track an empty reduced space.")
    overlap = np.empty(
        (len(previous.modes), len(current.modes)), dtype=np.float64
    )
    for row, previous_mode in enumerate(previous.modes):
        for column, current_mode in enumerate(current.modes):
            overlap[row, column] = abs(
                _qep_overlap(
                    operators,
                    previous_mode.left_reduced,
                    np.conj(previous_mode.left_adjoint_beta),
                    current_mode.right.right_reduced,
                    current_mode.beta,
                )
            )
    rows, columns = linear_sum_assignment(-overlap)
    matches = tuple(
        ModeTrackingMatch(
            previous_index=int(row),
            current_index=int(column),
            overlap=float(overlap[int(row), int(column)]),
            relative_beta_change=_relative_beta_distance(
                previous.modes[int(row)].beta,
                current.modes[int(column)].beta,
            ),
        )
        for row, column in zip(rows, columns)
    )
    matched_previous = {match.previous_index for match in matches}
    matched_current = {match.current_index for match in matches}
    current_by_previous = {
        match.previous_index: match.current_index for match in matches
    }
    subspaces: list[SubspaceTrackingReport] = []
    for group in previous.groups:
        if len(group.indices) < 2 or any(
            index not in current_by_previous for index in group.indices
        ):
            continue
        current_indices = tuple(current_by_previous[index] for index in group.indices)
        subspaces.append(
            _subspace_report(
                operators.electric_mass,
                previous,
                current,
                group.indices,
                current_indices,
            )
        )
    return ModeTrackingReport(
        matches=matches,
        unmatched_previous=tuple(
            index
            for index in range(len(previous.modes))
            if index not in matched_previous
        ),
        unmatched_current=tuple(
            index
            for index in range(len(current.modes))
            if index not in matched_current
        ),
        subspaces=tuple(subspaces),
        overlap_matrix=overlap,
    )
