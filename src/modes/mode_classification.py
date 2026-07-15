from __future__ import annotations

from dataclasses import dataclass
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
    solve_quadratic_beta_modes,
)


ModeDirection = Literal["forward", "backward", "ambiguous"]
ModeKind = Literal[
    "propagating",
    "lossy_propagating",
    "evanescent",
    "cutoff_or_near_zero_flux",
]


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
    adjoint_solver_report: QuadraticBetaSolveReport
    left_pair_relative_errors: tuple[float, ...]
    full_vector_gathered: bool = False

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


def _biorthogonality_matrix(
    operators: QuadraticBetaOperators,
    betas: Sequence[complex],
    left_vectors: Sequence[PETSc.Vec],
    right_vectors: Sequence[PETSc.Vec],
) -> np.ndarray:
    matrix = np.empty((len(betas), len(betas)), dtype=np.complex128)
    for row, (beta_left, left) in enumerate(zip(betas, left_vectors)):
        for column, (beta_right, right) in enumerate(zip(betas, right_vectors)):
            matrix[row, column] = _qep_overlap(
                operators, left, beta_left, right, beta_right
            )
    return matrix


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
    block_rotation_tolerance: float = 1.0e-8,
    maximum_overlap_condition: float = 1.0e12,
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

        pairing_cost = np.empty(
            (len(right_modes), len(left_candidates)), dtype=np.float64
        )
        for row, right in enumerate(right_modes):
            for column, left in enumerate(left_candidates):
                beta_error = _relative_beta_distance(
                    np.conj(left.beta), right.beta
                )
                overlap = abs(
                    _qep_overlap(
                        operators,
                        left.right_reduced,
                        right.beta,
                        right.right_reduced,
                        right.beta,
                    )
                )
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
        left_reduced = [mode.right_reduced for mode in left_candidates]
        left_full = [mode.right_full for mode in left_candidates]
        group_indices = _near_degenerate_groups(
            betas,
            relative_tolerance=near_degenerate_tolerance,
            absolute_tolerance=1.0e-12,
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
            raw_overlap = np.empty(
                (len(indices), len(indices)), dtype=np.complex128
            )
            for local_row, global_row in enumerate(indices):
                for local_column, global_column in enumerate(indices):
                    raw_overlap[local_row, local_column] = _qep_overlap(
                        operators,
                        left_reduced[global_row],
                        betas[global_row],
                        right_modes[global_column].right_reduced,
                        betas[global_column],
                    )
            condition = float(np.linalg.cond(raw_overlap))
            if not np.isfinite(condition) or condition > maximum_overlap_condition:
                raise RuntimeError(
                    "Near-degenerate left/right overlap is singular or ill-conditioned: "
                    f"indices={indices}, condition={condition:.6e}."
                )

            if len(indices) > 1 and spread <= block_rotation_tolerance:
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
                method = "near_degenerate_block_inverse"
            else:
                for global_index in indices:
                    diagonal = _qep_overlap(
                        operators,
                        left_reduced[global_index],
                        betas[global_index],
                        right_modes[global_index].right_reduced,
                        betas[global_index],
                    )
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

        biorthogonality = _biorthogonality_matrix(
            operators,
            betas,
            left_reduced,
            [mode.right_reduced for mode in right_modes],
        )
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

        return BiorthogonalModeBasis(
            modes=classified,
            groups=tuple(groups),
            biorthogonality_matrix=biorthogonality,
            max_identity_error=float(
                np.linalg.norm(
                    biorthogonality - np.eye(len(right_modes)), ord=np.inf
                )
            ),
            adjoint_solver_report=adjoint_report,
            left_pair_relative_errors=left_pair_errors,
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
                    previous_mode.beta,
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
