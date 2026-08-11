from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, Protocol, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment


PropagationDirection = Literal["forward", "backward"]
AxialPropagationModel = Literal["continuous_beta", "full3d_uniform_cg"]
ModalTractionModel = Literal[
    "continuous_qep_beta",
    "scalar_cg_discrete_derivative",
    "full3d_one_cell_exact_schur",
]


class ClassifiedModeForPropagation(Protocol):
    """Minimal Phase 3 mode interface consumed by the propagation block."""

    beta: complex
    direction: str
    passive_branch_valid: bool


@dataclass(frozen=True)
class DirectionalPropagationBlock:
    """One diagonal, physically directed propagation block.

    ``forward`` maps bottom-interface amplitudes to the top interface and
    ``backward`` maps top-interface amplitudes to the bottom interface.  The
    block never stores an inverse propagation factor.
    """

    direction: PropagationDirection
    length_nm: float
    source_indices: tuple[int, ...]
    beta_per_nm: tuple[complex, ...]
    effective_beta_per_nm: tuple[complex, ...]
    propagation_model: AxialPropagationModel
    factors: tuple[complex, ...]
    log_magnitudes: tuple[float, ...]
    phase_advances_rad: tuple[float, ...]
    phase_corrections_rad: tuple[float, ...]
    log_magnitude_corrections: tuple[float, ...]
    roundoff_growth_clipped: tuple[bool, ...]

    @property
    def mode_count(self) -> int:
        return len(self.factors)

    @property
    def max_factor_magnitude(self) -> float:
        return max((abs(value) for value in self.factors), default=0.0)

    @property
    def min_log_magnitude(self) -> float:
        return min(self.log_magnitudes, default=0.0)

    def apply(self, incoming: Sequence[complex] | np.ndarray) -> np.ndarray:
        amplitudes = np.asarray(incoming, dtype=np.complex128)
        if amplitudes.ndim != 1 or amplitudes.size != self.mode_count:
            raise ValueError(
                f"{self.direction} incoming amplitudes must have shape "
                f"({self.mode_count},), got {amplitudes.shape}."
            )
        return np.asarray(self.factors, dtype=np.complex128) * amplitudes


@dataclass(frozen=True)
class TwoPortOutgoingAmplitudes:
    """Outgoing ordering for ``incoming=[bottom_forward, top_backward]``."""

    bottom_backward: np.ndarray
    top_forward: np.ndarray


@dataclass(frozen=True)
class TwoSidedPropagation:
    """Reflection-free scattering representation of one uniform z segment."""

    length_nm: float
    forward: DirectionalPropagationBlock
    backward: DirectionalPropagationBlock
    propagation_model: AxialPropagationModel = "continuous_beta"
    representation: str = "two_port_diagonal_scattering"
    local_reflection_terms_present: bool = False
    growing_inverse_factors_present: bool = False

    @property
    def stored_complex_scalars(self) -> int:
        """O(mode-count) storage, excluding caller-owned amplitudes."""

        return self.forward.mode_count + self.backward.mode_count

    @property
    def max_factor_magnitude(self) -> float:
        return max(
            self.forward.max_factor_magnitude,
            self.backward.max_factor_magnitude,
        )

    @property
    def passivity_valid(self) -> bool:
        tolerance = 64.0 * np.finfo(np.float64).eps
        return bool(
            not self.growing_inverse_factors_present
            and self.max_factor_magnitude <= 1.0 + tolerance
        )

    def apply(
        self,
        bottom_forward: Sequence[complex] | np.ndarray,
        top_backward: Sequence[complex] | np.ndarray,
    ) -> TwoPortOutgoingAmplitudes:
        """Map incoming port amplitudes to reflection-free outgoing ports."""

        return TwoPortOutgoingAmplitudes(
            bottom_backward=self.backward.apply(top_backward),
            top_forward=self.forward.apply(bottom_forward),
        )

    def compose(self, following: TwoSidedPropagation) -> TwoSidedPropagation:
        """Return ``following(self(.))`` without forming a transfer matrix."""

        _require_compatible_blocks(self.forward, following.forward)
        _require_compatible_blocks(self.backward, following.backward)
        return TwoSidedPropagation(
            length_nm=self.length_nm + following.length_nm,
            forward=_compose_directional_blocks(self.forward, following.forward),
            backward=_compose_directional_blocks(self.backward, following.backward),
            propagation_model=self.propagation_model,
        )


@dataclass(frozen=True)
class ReciprocalPropagationPair:
    forward_local_index: int
    backward_local_index: int
    relative_beta_error: float
    relative_factor_error: float


@dataclass(frozen=True)
class ReciprocityPassivityDiagnostic:
    pairs: tuple[ReciprocalPropagationPair, ...]
    unmatched_forward: tuple[int, ...]
    unmatched_backward: tuple[int, ...]
    max_relative_beta_error: float
    max_relative_factor_error: float
    max_factor_magnitude: float
    reciprocity_tolerance: float
    reciprocity_valid: bool
    passivity_valid: bool


def _stable_factor(
    beta_per_nm: complex,
    length_nm: float,
    direction: PropagationDirection,
    *,
    branch_imag_tolerance_per_nm: float,
    roundoff_growth_tolerance: float,
) -> tuple[complex, float, float, bool]:
    beta = complex(beta_per_nm)
    if not np.isfinite(beta.real) or not np.isfinite(beta.imag):
        raise ValueError("Propagation beta must be finite.")

    travel_sign = 1.0 if direction == "forward" else -1.0
    signed_imag = travel_sign * beta.imag
    if signed_imag < -branch_imag_tolerance_per_nm:
        raise ValueError(
            f"{direction} beta={beta!r} grows along its physical travel "
            "direction; select the passive Phase 3 branch instead."
        )

    log_magnitude = -signed_imag * length_nm
    if log_magnitude > roundoff_growth_tolerance:
        raise ValueError(
            "Propagation would require a growing exponential; ordinary "
            "transfer-matrix inverse propagation is prohibited."
        )
    clipped = log_magnitude > 0.0
    stable_log_magnitude = min(log_magnitude, 0.0)
    phase = travel_sign * beta.real * length_nm
    with np.errstate(under="ignore", over="raise", invalid="raise"):
        magnitude = float(np.exp(stable_log_magnitude))
    factor = complex(magnitude * np.cos(phase), magnitude * np.sin(phase))
    if not np.isfinite(factor.real) or not np.isfinite(factor.imag):
        raise FloatingPointError("Non-finite stable propagation factor.")
    return factor, stable_log_magnitude, phase, clipped


@lru_cache(maxsize=None)
def _scalar_cg_reference_matrices(
    degree: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the 1D CG mass and stiffness matrices on ``[0, 1]``."""

    degree = int(degree)
    if degree < 1:
        raise ValueError("Axial FEM degree must be at least one.")
    nodes = np.linspace(0.0, 1.0, degree + 1)
    quadrature_x, quadrature_w = np.polynomial.legendre.leggauss(degree + 2)
    quadrature_x = 0.5 * (quadrature_x + 1.0)
    quadrature_w = 0.5 * quadrature_w
    values = np.empty((degree + 1, quadrature_x.size), dtype=np.float64)
    derivatives = np.empty_like(values)
    for basis_index, node in enumerate(nodes):
        polynomial = np.polynomial.Polynomial([1.0])
        denominator = 1.0
        for other_index, other_node in enumerate(nodes):
            if other_index == basis_index:
                continue
            polynomial *= np.polynomial.Polynomial([-other_node, 1.0])
            denominator *= node - other_node
        polynomial /= denominator
        values[basis_index, :] = polynomial(quadrature_x)
        derivatives[basis_index, :] = polynomial.deriv()(quadrature_x)
    mass = np.einsum("iq,q,jq->ij", values, quadrature_w, values)
    stiffness = np.einsum("iq,q,jq->ij", derivatives, quadrature_w, derivatives)
    mass.setflags(write=False)
    stiffness.setflags(write=False)
    return mass, stiffness


def _scalar_cg_periodic_cosine(
    q_direction: complex,
    degree: int,
) -> complex:
    """Return ``cos(theta)`` for one uniform scalar CG(p) cell."""

    y = q_direction * q_direction
    if degree == 2:
        numerator = np.polynomial.polynomial.polyval(
            y,
            (240.0, -104.0, 3.0),
        )
        denominator = np.polynomial.polynomial.polyval(
            y,
            (240.0, 16.0, 1.0),
        )
        cosine_theta = numerator / denominator
    elif degree == 6:
        numerator = np.polynomial.polynomial.polyval(
            y,
            (
                821_966_745_600.0,
                -393_739_315_200.0,
                25_826_169_600.0,
                -521_182_080.0,
                3_900_960.0,
                -10_416.0,
                7.0,
            ),
        )
        denominator = np.polynomial.polynomial.polyval(
            y,
            (
                821_966_745_600.0,
                17_244_057_600.0,
                199_584_000.0,
                1_728_000.0,
                12_960.0,
                96.0,
                1.0,
            ),
        )
        cosine_theta = numerator / denominator
    else:
        mass, stiffness = _scalar_cg_reference_matrices(degree)
        dynamic = stiffness.astype(np.complex128) - q_direction * q_direction * mass
        interior = list(range(1, degree))
        leading = dynamic[np.ix_([0, *interior], [0, *interior])]
        coupling = dynamic[np.ix_([0, *interior], [degree, *interior])]
        leading_sign, leading_logabs = np.linalg.slogdet(leading)
        coupling_sign, coupling_logabs = np.linalg.slogdet(coupling)
        if leading_sign == 0.0 or coupling_sign == 0.0:
            raise ValueError("Axial CG periodic-chain determinant ratio is singular.")
        cosine_theta = -(
            leading_sign / coupling_sign * np.exp(leading_logabs - coupling_logabs)
        )
    cosine_theta = complex(cosine_theta)
    if abs(q_direction.imag) <= 1.0e-14 and abs(cosine_theta.imag) <= 1.0e-14:
        if abs(cosine_theta.real - 1.0) <= 1.0e-12:
            cosine_theta = 1.0 + 0.0j
        elif abs(cosine_theta.real + 1.0) <= 1.0e-12:
            cosine_theta = -1.0 + 0.0j
    return cosine_theta


def full3d_uniform_cg_discrete_beta(
    beta_per_nm: complex,
    *,
    degree: int,
    h_nm: float,
    direction: PropagationDirection = "forward",
) -> complex:
    """Return the uniform CG(p) Bloch wavenumber nearest to ``beta``.

    This condenses the interior nodes of the scalar one-cell dynamic stiffness
    ``K - (beta*h)^2 M`` and applies its periodic-chain dispersion relation.
    The result models the z-directed polynomial factor in the tensor-product
    Full3D H(curl) discretization without changing the transverse QEP.
    """

    beta = complex(beta_per_nm)
    h_nm = float(h_nm)
    degree = int(degree)
    if not np.isfinite(beta.real) or not np.isfinite(beta.imag):
        raise ValueError("Axial beta must be finite.")
    if not np.isfinite(h_nm) or h_nm <= 0.0:
        raise ValueError("Axial h_nm must be finite and positive.")
    if direction not in ("forward", "backward"):
        raise ValueError(f"Unsupported propagation direction {direction!r}.")
    travel_sign = 1.0 if direction == "forward" else -1.0
    q_direction = travel_sign * beta * h_nm
    if q_direction.imag < -1.0e-12:
        raise ValueError(
            f"{direction} beta={beta!r} is not passive for axial CG mapping."
        )
    cosine_theta = _scalar_cg_periodic_cosine(
        q_direction,
        degree,
    )
    discriminant = complex(np.sqrt(cosine_theta * cosine_theta - 1.0))
    raw_roots = (
        complex(cosine_theta + discriminant),
        complex(cosine_theta - discriminant),
    )
    passive_roots = [
        root
        for root in raw_roots
        if (
            np.isfinite(root.real)
            and np.isfinite(root.imag)
            and abs(root) > 0.0
            and abs(root) <= 1.0 + 1.0e-10
        )
    ]
    if not passive_roots:
        largest = max(raw_roots, key=abs)
        if not np.isfinite(largest.real) or not np.isfinite(largest.imag):
            raise FloatingPointError("Non-finite axial CG Bloch roots.")
        if abs(largest) == 0.0:
            raise ValueError("Both axial CG Bloch roots vanished.")
        passive_roots = [1.0 / largest]
    candidates: list[complex] = []
    for root in passive_roots:
        principal = complex(-1j * np.log(root))
        nearest_shift = int(
            np.rint((q_direction.real - principal.real) / (2.0 * np.pi))
        )
        for shift in range(nearest_shift - 2, nearest_shift + 3):
            candidate = principal + 2.0 * np.pi * shift
            if candidate.imag >= -1.0e-10:
                candidates.append(candidate)
    if not candidates:
        raise ValueError("No passive axial CG Bloch branch was found.")
    theta_direction = min(
        candidates, key=lambda candidate: abs(candidate - q_direction)
    )
    effective_beta = travel_sign * theta_direction / h_nm
    if not np.isfinite(effective_beta.real) or not np.isfinite(effective_beta.imag):
        raise FloatingPointError("Non-finite Full3D-compatible axial beta.")
    return complex(effective_beta)


def scalar_cg_discrete_traction_beta(
    beta_per_nm: complex,
    *,
    degree: int,
    h_nm: float,
    direction: PropagationDirection,
) -> complex:
    """Return the scalar CG endpoint-derivative symbol as an effective beta."""

    try:
        beta = complex(beta_per_nm)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Scalar CG traction beta must be a complex scalar.") from exc
    try:
        degree_value = float(degree)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Scalar CG traction degree must be an integer.") from exc
    try:
        h_nm = float(h_nm)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Scalar CG traction h_nm must be a real scalar.") from exc
    if not np.isfinite(beta.real) or not np.isfinite(beta.imag):
        raise ValueError("Scalar CG traction beta must be finite.")
    if not np.isfinite(degree_value) or not degree_value.is_integer():
        raise ValueError("Scalar CG traction degree must be an integer.")
    degree = int(degree_value)
    if degree < 1 or degree > 6:
        raise ValueError("Scalar CG traction degree must lie in [1, 6].")
    if not np.isfinite(h_nm) or h_nm <= 0.0:
        raise ValueError("Scalar CG traction h_nm must be finite and positive.")
    if direction not in ("forward", "backward"):
        raise ValueError(f"Unsupported scalar CG traction direction {direction!r}.")
    travel_sign = 1.0 if direction == "forward" else -1.0
    q_direction = travel_sign * beta * h_nm
    if q_direction.imag < -1.0e-12:
        raise ValueError(
            f"{direction} beta={beta!r} is not passive for scalar CG traction."
        )
    mass, stiffness = _scalar_cg_reference_matrices(degree)
    dynamic = stiffness.astype(np.complex128) - q_direction * q_direction * mass
    interior = list(range(1, degree))
    if interior:
        interior_block = dynamic[np.ix_(interior, interior)]
        coupling_border = dynamic[np.ix_([0, *interior], [degree, *interior])]
        interior_sign, interior_logabs = np.linalg.slogdet(interior_block)
        coupling_sign, coupling_logabs = np.linalg.slogdet(coupling_border)
        if interior_sign == 0.0:
            raise ValueError(
                "Scalar CG traction is singular at an interior Dirichlet resonance."
            )
        if coupling_sign == 0.0:
            raise ValueError("Scalar CG traction endpoint coupling is singular.")
        with np.errstate(over="raise", invalid="raise", under="ignore"):
            off_diagonal = complex(
                coupling_sign
                / interior_sign
                * np.exp(coupling_logabs - interior_logabs)
            )
    else:
        off_diagonal = complex(dynamic[0, degree])
    effective_beta = full3d_uniform_cg_discrete_beta(
        beta,
        degree=degree,
        h_nm=h_nm,
        direction=direction,
    )
    theta_direction = travel_sign * effective_beta * h_nm
    multiplier = complex(np.exp(1j * theta_direction))
    if multiplier == 0.0:
        raise ValueError("Scalar CG traction Bloch multiplier underflowed.")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        outward_flux = 0.5 * off_diagonal * (multiplier - 1.0 / multiplier) / h_nm
    traction_beta = 1j * outward_flux if direction == "forward" else -1j * outward_flux
    if not np.isfinite(traction_beta.real) or not np.isfinite(traction_beta.imag):
        raise FloatingPointError("Non-finite scalar CG traction beta.")
    return complex(traction_beta)


def _build_directional_block(
    modes: Sequence[ClassifiedModeForPropagation],
    indices: Sequence[int],
    direction: PropagationDirection,
    length_nm: float,
    *,
    branch_imag_tolerance_per_nm: float,
    roundoff_growth_tolerance: float,
    propagation_model: AxialPropagationModel,
    axial_fem_degree: int | None,
    axial_h_nm: float | None,
) -> DirectionalPropagationBlock:
    betas: list[complex] = []
    effective_betas: list[complex] = []
    factors: list[complex] = []
    log_magnitudes: list[float] = []
    phases: list[float] = []
    phase_corrections: list[float] = []
    log_magnitude_corrections: list[float] = []
    clipped: list[bool] = []
    for index in indices:
        mode = modes[index]
        if not bool(mode.passive_branch_valid):
            raise ValueError(
                f"Mode {index} was not certified as a passive Phase 3 branch."
            )
        beta = complex(mode.beta)
        effective_beta = beta
        if propagation_model == "full3d_uniform_cg":
            assert axial_fem_degree is not None
            assert axial_h_nm is not None
            effective_beta = full3d_uniform_cg_discrete_beta(
                beta,
                degree=axial_fem_degree,
                h_nm=axial_h_nm,
                direction=direction,
            )
        factor, log_magnitude, phase, was_clipped = _stable_factor(
            effective_beta,
            length_nm,
            direction,
            branch_imag_tolerance_per_nm=branch_imag_tolerance_per_nm,
            roundoff_growth_tolerance=roundoff_growth_tolerance,
        )
        betas.append(beta)
        effective_betas.append(effective_beta)
        factors.append(factor)
        log_magnitudes.append(log_magnitude)
        phases.append(phase)
        travel_sign = 1.0 if direction == "forward" else -1.0
        phase_corrections.append(
            travel_sign * (effective_beta.real - beta.real) * length_nm
        )
        original_log_magnitude = min(
            -travel_sign * beta.imag * length_nm,
            0.0,
        )
        log_magnitude_corrections.append(log_magnitude - original_log_magnitude)
        clipped.append(was_clipped)
    return DirectionalPropagationBlock(
        direction=direction,
        length_nm=length_nm,
        source_indices=tuple(int(index) for index in indices),
        beta_per_nm=tuple(betas),
        effective_beta_per_nm=tuple(effective_betas),
        propagation_model=propagation_model,
        factors=tuple(factors),
        log_magnitudes=tuple(log_magnitudes),
        phase_advances_rad=tuple(phases),
        phase_corrections_rad=tuple(phase_corrections),
        log_magnitude_corrections=tuple(log_magnitude_corrections),
        roundoff_growth_clipped=tuple(clipped),
    )


def build_two_sided_propagation(
    modes: Sequence[ClassifiedModeForPropagation],
    length_nm: float,
    *,
    branch_imag_tolerance_per_nm: float = 1.0e-12,
    roundoff_growth_tolerance: float = 1.0e-12,
    propagation_model: AxialPropagationModel = "continuous_beta",
    axial_fem_degree: int | None = None,
    axial_h_nm: float | None = None,
) -> TwoSidedPropagation:
    """Build a passive two-port propagation block from Phase 3 modes."""

    length_nm = float(length_nm)
    if not np.isfinite(length_nm) or length_nm < 0.0:
        raise ValueError("Propagation length_nm must be finite and non-negative.")
    if branch_imag_tolerance_per_nm < 0.0:
        raise ValueError("branch_imag_tolerance_per_nm must be non-negative.")
    if roundoff_growth_tolerance < 0.0:
        raise ValueError("roundoff_growth_tolerance must be non-negative.")
    if propagation_model not in ("continuous_beta", "full3d_uniform_cg"):
        raise ValueError(f"Unsupported propagation_model {propagation_model!r}.")
    if propagation_model == "full3d_uniform_cg":
        if axial_fem_degree is None or int(axial_fem_degree) < 1:
            raise ValueError(
                "full3d_uniform_cg propagation requires axial_fem_degree >= 1."
            )
        if axial_h_nm is None or not np.isfinite(axial_h_nm) or axial_h_nm <= 0:
            raise ValueError(
                "full3d_uniform_cg propagation requires positive axial_h_nm."
            )
        cell_count = length_nm / float(axial_h_nm)
        if not np.isclose(cell_count, np.rint(cell_count), rtol=0.0, atol=1.0e-12):
            raise ValueError(
                "full3d_uniform_cg propagation requires an integer number of "
                "uniform axial cells across length_nm."
            )

    forward_indices: list[int] = []
    backward_indices: list[int] = []
    for index, mode in enumerate(modes):
        if mode.direction == "forward":
            forward_indices.append(index)
        elif mode.direction == "backward":
            backward_indices.append(index)
        else:
            raise ValueError(
                f"Mode {index} has ambiguous direction {mode.direction!r}; "
                "cutoff modes require a resolved physical branch first."
            )
    if not forward_indices or not backward_indices:
        raise ValueError(
            "Stable two-sided propagation requires at least one forward and "
            "one backward mode."
        )

    propagation = TwoSidedPropagation(
        length_nm=length_nm,
        forward=_build_directional_block(
            modes,
            forward_indices,
            "forward",
            length_nm,
            branch_imag_tolerance_per_nm=branch_imag_tolerance_per_nm,
            roundoff_growth_tolerance=roundoff_growth_tolerance,
            propagation_model=propagation_model,
            axial_fem_degree=axial_fem_degree,
            axial_h_nm=axial_h_nm,
        ),
        backward=_build_directional_block(
            modes,
            backward_indices,
            "backward",
            length_nm,
            branch_imag_tolerance_per_nm=branch_imag_tolerance_per_nm,
            roundoff_growth_tolerance=roundoff_growth_tolerance,
            propagation_model=propagation_model,
            axial_fem_degree=axial_fem_degree,
            axial_h_nm=axial_h_nm,
        ),
        propagation_model=propagation_model,
    )
    if not propagation.passivity_valid:
        raise ValueError("Stable propagation factors violate passivity.")
    return propagation


def _require_compatible_blocks(
    first: DirectionalPropagationBlock,
    second: DirectionalPropagationBlock,
) -> None:
    if first.direction != second.direction:
        raise ValueError("Cannot compose propagation blocks of different direction.")
    if first.source_indices != second.source_indices:
        raise ValueError("Cannot compose blocks with different mode ordering.")
    if first.propagation_model != second.propagation_model:
        raise ValueError("Cannot compose blocks with different propagation models.")
    if len(first.beta_per_nm) != len(second.beta_per_nm) or not np.allclose(
        first.beta_per_nm,
        second.beta_per_nm,
        rtol=1.0e-13,
        atol=1.0e-15,
    ):
        raise ValueError("Cannot compose blocks with different beta branches.")
    if not np.allclose(
        first.effective_beta_per_nm,
        second.effective_beta_per_nm,
        rtol=1.0e-13,
        atol=1.0e-15,
    ):
        raise ValueError("Cannot compose blocks with different effective beta.")


def _compose_directional_blocks(
    first: DirectionalPropagationBlock,
    second: DirectionalPropagationBlock,
) -> DirectionalPropagationBlock:
    factors = tuple(
        complex(second_value * first_value)
        for first_value, second_value in zip(first.factors, second.factors)
    )
    return DirectionalPropagationBlock(
        direction=first.direction,
        length_nm=first.length_nm + second.length_nm,
        source_indices=first.source_indices,
        beta_per_nm=first.beta_per_nm,
        effective_beta_per_nm=first.effective_beta_per_nm,
        propagation_model=first.propagation_model,
        factors=factors,
        log_magnitudes=tuple(
            first_value + second_value
            for first_value, second_value in zip(
                first.log_magnitudes, second.log_magnitudes
            )
        ),
        phase_advances_rad=tuple(
            first_value + second_value
            for first_value, second_value in zip(
                first.phase_advances_rad, second.phase_advances_rad
            )
        ),
        phase_corrections_rad=tuple(
            first_value + second_value
            for first_value, second_value in zip(
                first.phase_corrections_rad,
                second.phase_corrections_rad,
            )
        ),
        log_magnitude_corrections=tuple(
            first_value + second_value
            for first_value, second_value in zip(
                first.log_magnitude_corrections,
                second.log_magnitude_corrections,
            )
        ),
        roundoff_growth_clipped=tuple(
            first_value or second_value
            for first_value, second_value in zip(
                first.roundoff_growth_clipped,
                second.roundoff_growth_clipped,
            )
        ),
    )


def diagnose_reciprocity_and_passivity(
    propagation: TwoSidedPropagation,
    *,
    reciprocity_tolerance: float = 1.0e-8,
) -> ReciprocityPassivityDiagnostic:
    """Pair ``beta+`` with ``-beta-`` and compare directed factors."""

    if reciprocity_tolerance < 0.0:
        raise ValueError("reciprocity_tolerance must be non-negative.")
    forward_beta = np.asarray(propagation.forward.beta_per_nm, dtype=np.complex128)
    backward_beta = np.asarray(propagation.backward.beta_per_nm, dtype=np.complex128)
    cost = np.empty((forward_beta.size, backward_beta.size), dtype=float)
    for row, beta_forward in enumerate(forward_beta):
        for column, beta_backward in enumerate(backward_beta):
            cost[row, column] = abs(beta_forward + beta_backward) / max(
                abs(beta_forward), abs(beta_backward), 1.0e-15
            )
    rows, columns = linear_sum_assignment(cost)

    pairs: list[ReciprocalPropagationPair] = []
    forward_factors = propagation.forward.factors
    backward_factors = propagation.backward.factors
    for row, column in zip(rows, columns):
        factor_error = abs(
            forward_factors[int(row)] - backward_factors[int(column)]
        ) / max(
            abs(forward_factors[int(row)]),
            abs(backward_factors[int(column)]),
            1.0e-15,
        )
        pairs.append(
            ReciprocalPropagationPair(
                forward_local_index=int(row),
                backward_local_index=int(column),
                relative_beta_error=float(cost[int(row), int(column)]),
                relative_factor_error=float(factor_error),
            )
        )

    matched_forward = {pair.forward_local_index for pair in pairs}
    matched_backward = {pair.backward_local_index for pair in pairs}
    unmatched_forward = tuple(
        index for index in range(forward_beta.size) if index not in matched_forward
    )
    unmatched_backward = tuple(
        index for index in range(backward_beta.size) if index not in matched_backward
    )
    max_beta_error = max(
        (pair.relative_beta_error for pair in pairs), default=float("inf")
    )
    max_factor_error = max(
        (pair.relative_factor_error for pair in pairs), default=float("inf")
    )
    reciprocity_valid = bool(
        pairs
        and not unmatched_forward
        and not unmatched_backward
        and max_beta_error <= reciprocity_tolerance
        and max_factor_error <= reciprocity_tolerance
    )
    return ReciprocityPassivityDiagnostic(
        pairs=tuple(pairs),
        unmatched_forward=unmatched_forward,
        unmatched_backward=unmatched_backward,
        max_relative_beta_error=float(max_beta_error),
        max_relative_factor_error=float(max_factor_error),
        max_factor_magnitude=float(propagation.max_factor_magnitude),
        reciprocity_tolerance=float(reciprocity_tolerance),
        reciprocity_valid=reciprocity_valid,
        passivity_valid=propagation.passivity_valid,
    )
