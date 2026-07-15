from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment


PropagationDirection = Literal["forward", "backward"]


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
    factors: tuple[complex, ...]
    log_magnitudes: tuple[float, ...]
    phase_advances_rad: tuple[float, ...]
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


def _build_directional_block(
    modes: Sequence[ClassifiedModeForPropagation],
    indices: Sequence[int],
    direction: PropagationDirection,
    length_nm: float,
    *,
    branch_imag_tolerance_per_nm: float,
    roundoff_growth_tolerance: float,
) -> DirectionalPropagationBlock:
    betas: list[complex] = []
    factors: list[complex] = []
    log_magnitudes: list[float] = []
    phases: list[float] = []
    clipped: list[bool] = []
    for index in indices:
        mode = modes[index]
        if not bool(mode.passive_branch_valid):
            raise ValueError(
                f"Mode {index} was not certified as a passive Phase 3 branch."
            )
        beta = complex(mode.beta)
        factor, log_magnitude, phase, was_clipped = _stable_factor(
            beta,
            length_nm,
            direction,
            branch_imag_tolerance_per_nm=branch_imag_tolerance_per_nm,
            roundoff_growth_tolerance=roundoff_growth_tolerance,
        )
        betas.append(beta)
        factors.append(factor)
        log_magnitudes.append(log_magnitude)
        phases.append(phase)
        clipped.append(was_clipped)
    return DirectionalPropagationBlock(
        direction=direction,
        length_nm=length_nm,
        source_indices=tuple(int(index) for index in indices),
        beta_per_nm=tuple(betas),
        factors=tuple(factors),
        log_magnitudes=tuple(log_magnitudes),
        phase_advances_rad=tuple(phases),
        roundoff_growth_clipped=tuple(clipped),
    )


def build_two_sided_propagation(
    modes: Sequence[ClassifiedModeForPropagation],
    length_nm: float,
    *,
    branch_imag_tolerance_per_nm: float = 1.0e-12,
    roundoff_growth_tolerance: float = 1.0e-12,
) -> TwoSidedPropagation:
    """Build a passive two-port propagation block from Phase 3 modes."""

    length_nm = float(length_nm)
    if not np.isfinite(length_nm) or length_nm < 0.0:
        raise ValueError("Propagation length_nm must be finite and non-negative.")
    if branch_imag_tolerance_per_nm < 0.0:
        raise ValueError("branch_imag_tolerance_per_nm must be non-negative.")
    if roundoff_growth_tolerance < 0.0:
        raise ValueError("roundoff_growth_tolerance must be non-negative.")

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
        ),
        backward=_build_directional_block(
            modes,
            backward_indices,
            "backward",
            length_nm,
            branch_imag_tolerance_per_nm=branch_imag_tolerance_per_nm,
            roundoff_growth_tolerance=roundoff_growth_tolerance,
        ),
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
    if len(first.beta_per_nm) != len(second.beta_per_nm) or not np.allclose(
        first.beta_per_nm,
        second.beta_per_nm,
        rtol=1.0e-13,
        atol=1.0e-15,
    ):
        raise ValueError("Cannot compose blocks with different beta branches.")


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
