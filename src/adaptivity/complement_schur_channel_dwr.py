"""Algebraic missing-trace Schur and channel-DWR kernel for Task035b.

The fixed p5-trace/p6-interior solution is the retained (``L``) state.  A
caller that has assembled *physical* missing-p6-trace blocks may use this
module to evaluate

``r_H = b_H - A_HL u_L``,

``S_H = A_HH - A_HL A_LL^{-1} A_LH``, and

``q_H = g_H - A_LH^H z_L``.

The complement correction and adjoint are then

``delta_u_H = S_H^{-1} r_H`` and ``z_H = S_H^{-H} q_H``.  Consequently the
linearized channel error has the two independently evaluated forms

``q_H^H delta_u_H = z_H^H r_H``.

Only operator actions and caller-owned factor/solve callbacks are required.
In particular, this kernel never probes a ``LinearOperator`` column by column
and never materializes a full p6 matrix or inactive trace rows.

The implementation is deliberately an algebraic integration layer.  It does
not claim that h14 mesh entities, Piola/Floquet pullbacks, periodic numbering,
DtN/port derivatives, or inactive-row-free DOLFINx assembly have been wired
to it.  Those external integration gates remain explicitly ``not_run`` in
the returned audit.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Callable, Literal, Mapping, Sequence

import numpy as np
from scipy.linalg import qr


ComplexVector = np.ndarray
VectorAction = Callable[[ComplexVector], ComplexVector]
GoalComponent = Literal[
    "real_power",
    "complex_amplitude_real",
    "complex_amplitude_imag",
]

_GOAL_COMPONENTS = {
    "real_power",
    "complex_amplitude_real",
    "complex_amplitude_imag",
}


def _readonly_vector(
    values: np.ndarray,
    *,
    dimension: int | None,
    label: str,
) -> np.ndarray:
    vector = np.array(values, dtype=np.complex128, order="C", copy=True)
    if vector.ndim != 1:
        raise ValueError(f"{label} must be a vector")
    if dimension is not None and vector.shape != (int(dimension),):
        raise ValueError(
            f"{label} has shape {vector.shape}, expected {(dimension,)}"
        )
    if not np.all(np.isfinite(vector)):
        raise FloatingPointError(f"{label} contains NaN or Inf")
    vector.setflags(write=False)
    return vector


def _relative_residual(
    actual: np.ndarray,
    expected: np.ndarray,
) -> float:
    difference = float(np.linalg.norm(actual - expected))
    right_hand_side_norm = float(np.linalg.norm(expected))
    if right_hand_side_norm == 0.0:
        # A homogeneous solve has no meaningful relative denominator.  It
        # passes only if the computed action is also exactly homogeneous;
        # otherwise infinity makes the solve gate fail closed.
        return 0.0 if difference == 0.0 else float("inf")
    return difference / right_hand_side_norm


def _complex_record(value: complex) -> dict[str, float]:
    scalar = complex(value)
    return {"real": float(scalar.real), "imag": float(scalar.imag)}


def _component_value(value: complex, component: GoalComponent) -> float:
    if component in _GOAL_COMPONENTS:
        # Repository DtN convention: power, Re(amplitude), and Im(amplitude)
        # are three independent real-valued functionals, each with
        # dJ[du] = Re(g^H du).  The amplitude-imaginary gradient already
        # carries the required +i factor; taking Im(g^H du) here would apply
        # that rotation twice.
        return float(complex(value).real)
    raise ValueError(f"unsupported channel goal component: {component}")


class _LinearMap:
    """Checked vector actions without implicit dense materialization."""

    def __init__(
        self,
        operator: np.ndarray | Any | VectorAction,
        *,
        shape: tuple[int, int],
        adjoint_action: VectorAction | None,
        label: str,
    ) -> None:
        rows, columns = map(int, shape)
        if rows <= 0 or columns <= 0:
            raise ValueError(f"{label} shape must be positive")
        self.shape = (rows, columns)
        self.label = str(label)

        if isinstance(operator, np.ndarray):
            matrix = np.array(
                operator,
                dtype=np.complex128,
                order="C",
                copy=True,
            )
            if matrix.shape != self.shape:
                raise ValueError(
                    f"{label} has shape {matrix.shape}, "
                    f"expected {self.shape}"
                )
            if not np.all(np.isfinite(matrix)):
                raise FloatingPointError(f"{label} contains NaN or Inf")
            matrix.setflags(write=False)
            self._forward = lambda vector: matrix @ vector
            self._adjoint = lambda vector: matrix.conj().T @ vector
            self.storage_kind = "explicit_dense_block"
            return

        operator_shape = getattr(operator, "shape", None)
        if operator_shape is not None:
            actual_shape = tuple(map(int, operator_shape))
            if actual_shape != self.shape:
                raise ValueError(
                    f"{label} has shape {actual_shape}, "
                    f"expected {self.shape}"
                )

        if hasattr(operator, "matvec"):
            self._forward = operator.matvec
            if adjoint_action is not None:
                self._adjoint = adjoint_action
            elif hasattr(operator, "rmatvec"):
                self._adjoint = operator.rmatvec
            else:
                raise ValueError(f"{label} lacks an adjoint action")
            self.storage_kind = "linear_operator"
            return

        if not callable(operator):
            raise TypeError(
                f"{label} must be a dense block, LinearOperator, or callback"
            )
        if adjoint_action is None:
            raise ValueError(
                f"{label} callback requires an explicit adjoint action"
            )
        self._forward = operator
        self._adjoint = adjoint_action
        self.storage_kind = "callback"

    def apply(self, vector: np.ndarray) -> np.ndarray:
        argument = _readonly_vector(
            vector,
            dimension=self.shape[1],
            label=f"{self.label} input",
        )
        return _readonly_vector(
            self._forward(argument),
            dimension=self.shape[0],
            label=f"{self.label} output",
        )

    def apply_adjoint(self, vector: np.ndarray) -> np.ndarray:
        argument = _readonly_vector(
            vector,
            dimension=self.shape[0],
            label=f"{self.label} adjoint input",
        )
        return _readonly_vector(
            self._adjoint(argument),
            dimension=self.shape[1],
            label=f"{self.label} adjoint output",
        )


@dataclass(frozen=True)
class ChannelGoal:
    """One caller-qualified physical channel component.

    ``missing_gradient`` is ``g_H`` and ``retained_adjoint`` is ``z_L``.
    All three component kinds follow the repository's independent
    real-functional convention ``dJ[du] = Re(g^H du)``.  Thus a caller must
    provide the already rotated ``+i`` gradient for an amplitude-imaginary
    goal, exactly as :mod:`src.adaptivity.dtn_goal_adjoint` does.
    A protected goal must provide its current signed error relative to the
    frozen reference so that orbit-wise regression and gate-crossing flags
    have a defined meaning.  Its exact convention is
    ``baseline_signed_error = J_L - J_reference``; because complement DWR is
    ``J_enriched - J_L``, their sum is the predicted enriched error.
    """

    label: str
    component: GoalComponent
    tolerance: float
    missing_gradient: np.ndarray
    retained_adjoint: np.ndarray
    actual_channel_gradient: bool
    retained_adjoint_qualified: bool
    selection_target: bool = True
    selection_weight: float = 1.0
    protected: bool = False
    baseline_signed_error: float | None = None

    def __post_init__(self) -> None:
        label = str(self.label)
        if not label:
            raise ValueError("channel goal label must be non-empty")
        object.__setattr__(self, "label", label)
        if self.component not in _GOAL_COMPONENTS:
            raise ValueError(
                f"unsupported channel goal component: {self.component}"
            )
        tolerance = float(self.tolerance)
        if not np.isfinite(tolerance) or tolerance <= 0.0:
            raise ValueError("channel goal tolerance must be positive")
        object.__setattr__(self, "tolerance", tolerance)
        weight = float(self.selection_weight)
        if not np.isfinite(weight) or weight <= 0.0:
            raise ValueError("channel goal selection weight must be positive")
        object.__setattr__(self, "selection_weight", weight)
        object.__setattr__(
            self,
            "missing_gradient",
            _readonly_vector(
                self.missing_gradient,
                dimension=None,
                label=f"{label} missing gradient",
            ),
        )
        object.__setattr__(
            self,
            "retained_adjoint",
            _readonly_vector(
                self.retained_adjoint,
                dimension=None,
                label=f"{label} retained adjoint",
            ),
        )
        if self.protected and self.selection_target:
            raise ValueError(
                "channel goal cannot be both selection_target and protected"
            )
        if (
            self.protected or self.selection_target
        ) and self.baseline_signed_error is None:
            raise ValueError(
                "selection-target/protected channel goal requires a "
                "baseline signed error"
            )
        if self.baseline_signed_error is not None:
            baseline = float(self.baseline_signed_error)
            if not np.isfinite(baseline):
                raise ValueError(
                    "channel goal baseline signed error must be finite"
                )
            object.__setattr__(self, "baseline_signed_error", baseline)


@dataclass(frozen=True)
class WholeOrbitBlock:
    """Caller-certified complete periodic orbit in complement coordinates."""

    orbit_id: str
    complement_indices: tuple[int, ...]
    member_entity_ids: tuple[int, ...]
    periodic_orbit_closed: bool

    def __post_init__(self) -> None:
        orbit_id = str(self.orbit_id)
        if not orbit_id:
            raise ValueError("periodic orbit id must be non-empty")
        object.__setattr__(self, "orbit_id", orbit_id)
        indices = tuple(map(int, self.complement_indices))
        members = tuple(map(int, self.member_entity_ids))
        if not indices or len(set(indices)) != len(indices):
            raise ValueError(
                "periodic orbit complement indices must be nonempty and unique"
            )
        if min(indices) < 0:
            raise ValueError(
                "periodic orbit complement indices must be nonnegative"
            )
        if not members or len(set(members)) != len(members):
            raise ValueError(
                "periodic orbit entity ids must be nonempty and unique"
            )
        object.__setattr__(self, "complement_indices", indices)
        object.__setattr__(self, "member_entity_ids", members)


class ComplementSchurOperator:
    """Action-only missing-trace Schur complement with explicit solves."""

    def __init__(
        self,
        *,
        low_dimension: int,
        high_dimension: int,
        a_hh: np.ndarray | Any | VectorAction,
        a_hl: np.ndarray | Any | VectorAction,
        a_lh: np.ndarray | Any | VectorAction,
        a_ll_solve: VectorAction,
        a_ll_adjoint_solve: VectorAction,
        schur_solve: VectorAction,
        schur_adjoint_solve: VectorAction,
        a_hh_adjoint_action: VectorAction | None = None,
        a_hl_adjoint_action: VectorAction | None = None,
        a_lh_adjoint_action: VectorAction | None = None,
        solve_tolerance: float = 2.0e-11,
    ) -> None:
        low_dimension = int(low_dimension)
        high_dimension = int(high_dimension)
        if low_dimension <= 0 or high_dimension <= 0:
            raise ValueError("low/high complement dimensions must be positive")
        solve_tolerance = float(solve_tolerance)
        if not np.isfinite(solve_tolerance) or solve_tolerance <= 0.0:
            raise ValueError("Schur solve tolerance must be positive")
        for callback, label in (
            (a_ll_solve, "A_LL solve"),
            (a_ll_adjoint_solve, "A_LL adjoint solve"),
            (schur_solve, "Schur solve"),
            (schur_adjoint_solve, "Schur adjoint solve"),
        ):
            if not callable(callback):
                raise TypeError(f"{label} must be callable")

        self.low_dimension = low_dimension
        self.high_dimension = high_dimension
        self.solve_tolerance = solve_tolerance
        self._a_hh = _LinearMap(
            a_hh,
            shape=(high_dimension, high_dimension),
            adjoint_action=a_hh_adjoint_action,
            label="A_HH",
        )
        self._a_hl = _LinearMap(
            a_hl,
            shape=(high_dimension, low_dimension),
            adjoint_action=a_hl_adjoint_action,
            label="A_HL",
        )
        self._a_lh = _LinearMap(
            a_lh,
            shape=(low_dimension, high_dimension),
            adjoint_action=a_lh_adjoint_action,
            label="A_LH",
        )
        self._a_ll_solve = a_ll_solve
        self._a_ll_adjoint_solve = a_ll_adjoint_solve
        self._schur_solve = schur_solve
        self._schur_adjoint_solve = schur_adjoint_solve
        self.audit = MappingProxyType(
            {
                "schema_version": (
                    "task035b.complement-schur-operator.v1"
                ),
                "status": "action_only_algebraic_kernel_ready",
                "low_dimension": low_dimension,
                "high_dimension": high_dimension,
                "block_storage": {
                    "A_HH": self._a_hh.storage_kind,
                    "A_HL": self._a_hl.storage_kind,
                    "A_LH": self._a_lh.storage_kind,
                },
                "caller_owned_A_LL_factor_solve": True,
                "caller_owned_S_H_solve": True,
                "full_p6_matrix_materialized_by_kernel": False,
                "Schur_matrix_materialized_by_kernel": False,
                "inactive_p6_rows_allocated_by_kernel": False,
                "ordinary_default_changed": False,
            }
        )

    def _apply_solve(
        self,
        callback: VectorAction,
        right_hand_side: np.ndarray,
        *,
        dimension: int,
        label: str,
    ) -> np.ndarray:
        rhs = _readonly_vector(
            right_hand_side,
            dimension=dimension,
            label=f"{label} right-hand side",
        )
        return _readonly_vector(
            callback(rhs),
            dimension=dimension,
            label=f"{label} result",
        )

    def matvec(self, vector: np.ndarray) -> np.ndarray:
        """Apply ``S_H`` without constructing it."""

        high_vector = _readonly_vector(
            vector,
            dimension=self.high_dimension,
            label="Schur input",
        )
        low_action = self._a_lh.apply(high_vector)
        low_solution = self._apply_solve(
            self._a_ll_solve,
            low_action,
            dimension=self.low_dimension,
            label="A_LL",
        )
        return _readonly_vector(
            self._a_hh.apply(high_vector)
            - self._a_hl.apply(low_solution),
            dimension=self.high_dimension,
            label="Schur action",
        )

    def rmatvec(self, vector: np.ndarray) -> np.ndarray:
        """Apply ``S_H^H`` without constructing it."""

        high_vector = _readonly_vector(
            vector,
            dimension=self.high_dimension,
            label="adjoint Schur input",
        )
        low_action = self._a_hl.apply_adjoint(high_vector)
        low_solution = self._apply_solve(
            self._a_ll_adjoint_solve,
            low_action,
            dimension=self.low_dimension,
            label="A_LL adjoint",
        )
        return _readonly_vector(
            self._a_hh.apply_adjoint(high_vector)
            - self._a_lh.apply_adjoint(low_solution),
            dimension=self.high_dimension,
            label="adjoint Schur action",
        )

    def solve(self, right_hand_side: np.ndarray) -> np.ndarray:
        """Apply the caller's ``S_H^{-1}`` and verify its residual."""

        rhs = _readonly_vector(
            right_hand_side,
            dimension=self.high_dimension,
            label="Schur right-hand side",
        )
        solution = self._apply_solve(
            self._schur_solve,
            rhs,
            dimension=self.high_dimension,
            label="Schur",
        )
        residual = _relative_residual(self.matvec(solution), rhs)
        if residual > self.solve_tolerance:
            raise RuntimeError(
                "caller-supplied Schur solve failed the explicit residual "
                f"gate: {residual:.6e} > {self.solve_tolerance:.6e}"
            )
        return solution

    def solve_adjoint(self, right_hand_side: np.ndarray) -> np.ndarray:
        """Apply the caller's ``S_H^{-H}`` and verify its residual."""

        rhs = _readonly_vector(
            right_hand_side,
            dimension=self.high_dimension,
            label="adjoint Schur right-hand side",
        )
        solution = self._apply_solve(
            self._schur_adjoint_solve,
            rhs,
            dimension=self.high_dimension,
            label="adjoint Schur",
        )
        residual = _relative_residual(self.rmatvec(solution), rhs)
        if residual > self.solve_tolerance:
            raise RuntimeError(
                "caller-supplied adjoint Schur solve failed the explicit "
                f"residual gate: {residual:.6e} > "
                f"{self.solve_tolerance:.6e}"
            )
        return solution

    def primal_residual(
        self,
        *,
        missing_right_hand_side: np.ndarray,
        retained_state: np.ndarray,
    ) -> np.ndarray:
        """Return ``r_H = b_H - A_HL u_L``."""

        rhs = _readonly_vector(
            missing_right_hand_side,
            dimension=self.high_dimension,
            label="missing right-hand side",
        )
        retained = _readonly_vector(
            retained_state,
            dimension=self.low_dimension,
            label="retained state",
        )
        return _readonly_vector(
            rhs - self._a_hl.apply(retained),
            dimension=self.high_dimension,
            label="missing primal residual",
        )

    def goal_complement(
        self,
        *,
        missing_gradient: np.ndarray,
        retained_adjoint: np.ndarray,
    ) -> np.ndarray:
        """Return ``q_H = g_H - A_LH^H z_L``."""

        gradient = _readonly_vector(
            missing_gradient,
            dimension=self.high_dimension,
            label="missing goal gradient",
        )
        adjoint = _readonly_vector(
            retained_adjoint,
            dimension=self.low_dimension,
            label="retained adjoint",
        )
        return _readonly_vector(
            gradient - self._a_lh.apply_adjoint(adjoint),
            dimension=self.high_dimension,
            label="missing goal complement",
        )


@dataclass(frozen=True)
class ChannelDWRResult:
    """One exact algebraic complement-DWR result."""

    label: str
    component: GoalComponent
    tolerance: float
    goal_complement: np.ndarray
    complement_adjoint: np.ndarray
    correction_pairing: complex
    residual_weighted_pairing: complex
    signed_component_correction: float
    normalized_signed_correction: float
    normalized_magnitude: float
    identity_relative_error: float
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "goal_complement",
            _readonly_vector(
                self.goal_complement,
                dimension=None,
                label=f"{self.label} goal complement",
            ),
        )
        object.__setattr__(
            self,
            "complement_adjoint",
            _readonly_vector(
                self.complement_adjoint,
                dimension=None,
                label=f"{self.label} complement adjoint",
            ),
        )


@dataclass(frozen=True)
class OrbitDWRResult:
    """Whole-orbit residual-weighted contributions and regression flags."""

    orbit_id: str
    rank: int
    member_entity_ids: tuple[int, ...]
    complement_indices: tuple[int, ...]
    selection_score: float
    all_goal_score: float
    target_net_absolute_error_improvement: float
    target_regression_penalty: float
    target_regression_count: int
    target_gate_crossing_count: int
    target_gate_recovery_count: int
    protected_regression_count: int
    protected_gate_crossing_count: int
    goals: Mapping[str, Mapping[str, Any]]
    audit: Mapping[str, Any]


@dataclass(frozen=True)
class ComplementDWRAnalysis:
    """Multi-goal complement solve, DWR identities, and orbit ranking."""

    primal_residual: np.ndarray
    complement_correction: np.ndarray
    goals: Mapping[str, ChannelDWRResult]
    ranked_orbits: tuple[OrbitDWRResult, ...]
    svd_rrqr_diagnostics: Mapping[str, Any]
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "primal_residual",
            _readonly_vector(
                self.primal_residual,
                dimension=None,
                label="analysis primal residual",
            ),
        )
        object.__setattr__(
            self,
            "complement_correction",
            _readonly_vector(
                self.complement_correction,
                dimension=None,
                label="analysis complement correction",
            ),
        )


def _validate_orbit_partition(
    orbits: Sequence[WholeOrbitBlock],
    *,
    high_dimension: int,
) -> tuple[WholeOrbitBlock, ...]:
    blocks = tuple(orbits)
    if not blocks:
        raise ValueError("at least one complete periodic orbit is required")
    ids = [block.orbit_id for block in blocks]
    if len(set(ids)) != len(ids):
        raise ValueError("periodic orbit ids must be unique")
    for block in blocks:
        if block.periodic_orbit_closed is not True:
            raise RuntimeError(
                f"periodic orbit {block.orbit_id} is not certified closed"
            )
        if max(block.complement_indices) >= high_dimension:
            raise ValueError(
                f"periodic orbit {block.orbit_id} has an out-of-range index"
            )
    flattened = [
        index
        for block in blocks
        for index in block.complement_indices
    ]
    if len(flattened) != len(set(flattened)):
        raise ValueError("periodic orbit complement blocks overlap")
    expected = set(range(high_dimension))
    actual = set(flattened)
    if actual != expected:
        raise ValueError(
            "periodic orbit blocks must partition the active complement: "
            f"missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )
    return blocks


def evaluate_complement_channel_dwr(
    schur: ComplementSchurOperator,
    *,
    missing_right_hand_side: np.ndarray,
    retained_state: np.ndarray,
    goals: Sequence[ChannelGoal],
    orbits: Sequence[WholeOrbitBlock],
    identity_tolerance: float = 5.0e-11,
    protected_regression_slack: float = 1.0e-12,
) -> ComplementDWRAnalysis:
    """Evaluate actual algebraic channel DWR and rank complete orbits.

    The word ``actual`` here means that the Schur correction and complement
    adjoints are solved, rather than replaced by the unscaled ``q_H^H r_H``
    proxy.  Formal h14/DtN/mesh authority remains outside this function.
    """

    identity_tolerance = float(identity_tolerance)
    protected_regression_slack = float(protected_regression_slack)
    if not np.isfinite(identity_tolerance) or identity_tolerance <= 0.0:
        raise ValueError("DWR identity tolerance must be positive")
    if (
        not np.isfinite(protected_regression_slack)
        or protected_regression_slack < 0.0
    ):
        raise ValueError("protected regression slack must be nonnegative")

    goal_specs = tuple(goals)
    if not goal_specs:
        raise ValueError("at least one channel goal is required")
    labels = [goal.label for goal in goal_specs]
    if len(set(labels)) != len(labels):
        raise ValueError("channel goal labels must be unique")
    if not any(goal.selection_target for goal in goal_specs):
        raise ValueError("at least one channel goal must be a selection target")
    for goal in goal_specs:
        if goal.actual_channel_gradient is not True:
            raise RuntimeError(
                f"{goal.label} is not an actual channel gradient"
            )
        if goal.retained_adjoint_qualified is not True:
            raise RuntimeError(
                f"{goal.label} retained adjoint is not qualified"
            )
        if goal.missing_gradient.shape != (schur.high_dimension,):
            raise ValueError(
                f"{goal.label} missing gradient dimension differs"
            )
        if goal.retained_adjoint.shape != (schur.low_dimension,):
            raise ValueError(
                f"{goal.label} retained adjoint dimension differs"
            )

    orbit_blocks = _validate_orbit_partition(
        orbits,
        high_dimension=schur.high_dimension,
    )
    primal_residual = schur.primal_residual(
        missing_right_hand_side=missing_right_hand_side,
        retained_state=retained_state,
    )
    correction = schur.solve(primal_residual)

    channel_results: dict[str, ChannelDWRResult] = {}
    complement_adjoints: dict[str, np.ndarray] = {}
    for goal in goal_specs:
        goal_complement = schur.goal_complement(
            missing_gradient=goal.missing_gradient,
            retained_adjoint=goal.retained_adjoint,
        )
        complement_adjoint = schur.solve_adjoint(goal_complement)
        correction_pairing = complex(np.vdot(goal_complement, correction))
        residual_pairing = complex(
            np.vdot(complement_adjoint, primal_residual)
        )
        pairing_scale = max(
            1.0,
            abs(correction_pairing),
            abs(residual_pairing),
        )
        identity_error = float(
            abs(correction_pairing - residual_pairing) / pairing_scale
        )
        if identity_error > identity_tolerance:
            raise RuntimeError(
                f"{goal.label} complement DWR identity failed: "
                f"{identity_error:.6e} > {identity_tolerance:.6e}"
            )
        signed = _component_value(correction_pairing, goal.component)
        normalized_signed = float(signed / goal.tolerance)
        audit = MappingProxyType(
            {
                "schema_version": (
                    "task035b.complement-channel-dwr-goal.v1"
                ),
                "status": "actual_algebraic_complement_dwr_pass",
                "actual_missing_trace_primal_residual": True,
                "actual_missing_trace_complement_solve": True,
                "actual_missing_trace_adjoint_solve": True,
                "residual_weighted": True,
                "correction_pairing": _complex_record(
                    correction_pairing
                ),
                "residual_weighted_pairing": _complex_record(
                    residual_pairing
                ),
                "component_normalization": goal.component,
                "real_functional_convention": "dJ[du]=Re(g^H du)",
                "actual_channel_gradient_caller_qualified": True,
                "retained_adjoint_caller_qualified": True,
            }
        )
        channel_results[goal.label] = ChannelDWRResult(
            label=goal.label,
            component=goal.component,
            tolerance=goal.tolerance,
            goal_complement=goal_complement,
            complement_adjoint=complement_adjoint,
            correction_pairing=correction_pairing,
            residual_weighted_pairing=residual_pairing,
            signed_component_correction=signed,
            normalized_signed_correction=normalized_signed,
            normalized_magnitude=abs(normalized_signed),
            identity_relative_error=identity_error,
            audit=audit,
        )
        complement_adjoints[goal.label] = complement_adjoint

    orbit_results: list[OrbitDWRResult] = []
    normalized_matrix = np.zeros(
        (len(goal_specs), len(orbit_blocks)),
        dtype=np.float64,
    )
    for orbit_column, orbit in enumerate(orbit_blocks):
        indices = np.asarray(orbit.complement_indices, dtype=np.int64)
        goal_reports: dict[str, Mapping[str, Any]] = {}
        positive_target_improvements: list[float] = []
        target_regression_penalties: list[float] = []
        target_net_improvement = 0.0
        all_values: list[float] = []
        target_regression_count = 0
        target_crossing_count = 0
        target_recovery_count = 0
        regression_count = 0
        crossing_count = 0
        for goal_row, goal in enumerate(goal_specs):
            orbit_pairing = complex(
                np.vdot(
                    complement_adjoints[goal.label][indices],
                    primal_residual[indices],
                )
            )
            signed = _component_value(orbit_pairing, goal.component)
            normalized = float(signed / goal.tolerance)
            normalized_matrix[goal_row, orbit_column] = normalized
            weighted = float(goal.selection_weight * normalized)
            all_values.append(weighted)

            baseline_normalized: float | None = None
            predicted_normalized: float | None = None
            absolute_error_improvement: float | None = None
            target_regression = False
            target_gate_crossing = False
            target_gate_recovery = False
            protected_regression = False
            protected_gate_crossing = False
            if goal.baseline_signed_error is not None:
                baseline_normalized = float(
                    goal.baseline_signed_error / goal.tolerance
                )
                predicted_normalized = float(
                    baseline_normalized + normalized
                )
                absolute_error_improvement = float(
                    abs(baseline_normalized)
                    - abs(predicted_normalized)
                )
            if goal.selection_target:
                assert baseline_normalized is not None
                assert predicted_normalized is not None
                assert absolute_error_improvement is not None
                weighted_improvement = float(
                    goal.selection_weight * absolute_error_improvement
                )
                target_net_improvement += weighted_improvement
                positive_target_improvements.append(
                    max(0.0, weighted_improvement)
                )
                target_regression_penalties.append(
                    max(0.0, -weighted_improvement)
                )
                target_regression = bool(
                    absolute_error_improvement
                    < -protected_regression_slack
                )
                target_gate_crossing = bool(
                    abs(baseline_normalized)
                    <= 1.0 + protected_regression_slack
                    and abs(predicted_normalized)
                    > 1.0 + protected_regression_slack
                )
                target_gate_recovery = bool(
                    abs(baseline_normalized)
                    > 1.0 + protected_regression_slack
                    and abs(predicted_normalized)
                    <= 1.0 + protected_regression_slack
                )
                target_regression_count += int(target_regression)
                target_crossing_count += int(target_gate_crossing)
                target_recovery_count += int(target_gate_recovery)
            if goal.protected:
                assert baseline_normalized is not None
                assert predicted_normalized is not None
                protected_regression = bool(
                    abs(predicted_normalized)
                    > abs(baseline_normalized)
                    + protected_regression_slack
                )
                protected_gate_crossing = bool(
                    abs(baseline_normalized)
                    <= 1.0 + protected_regression_slack
                    and abs(predicted_normalized)
                    > 1.0 + protected_regression_slack
                )
                regression_count += int(protected_regression)
                crossing_count += int(protected_gate_crossing)

            goal_reports[goal.label] = MappingProxyType(
                {
                    "component": goal.component,
                    "complex_orbit_dwr": _complex_record(orbit_pairing),
                    "signed_component_correction": signed,
                    "normalized_signed_correction": normalized,
                    "normalized_magnitude": abs(normalized),
                    "selection_target": goal.selection_target,
                    "selection_weight": goal.selection_weight,
                    "protected": goal.protected,
                    "baseline_normalized_signed_error": (
                        baseline_normalized
                    ),
                    "predicted_normalized_signed_error": (
                        predicted_normalized
                    ),
                    "normalized_absolute_error_improvement": (
                        absolute_error_improvement
                    ),
                    "target_regression": target_regression,
                    "target_gate_crossing": target_gate_crossing,
                    "target_gate_recovery": target_gate_recovery,
                    "protected_regression": protected_regression,
                    "protected_gate_crossing": protected_gate_crossing,
                }
            )
        orbit_results.append(
            OrbitDWRResult(
                orbit_id=orbit.orbit_id,
                rank=0,
                member_entity_ids=orbit.member_entity_ids,
                complement_indices=orbit.complement_indices,
                selection_score=float(
                    np.linalg.norm(positive_target_improvements)
                ),
                all_goal_score=float(np.linalg.norm(all_values)),
                target_net_absolute_error_improvement=float(
                    target_net_improvement
                ),
                target_regression_penalty=float(
                    np.linalg.norm(target_regression_penalties)
                ),
                target_regression_count=target_regression_count,
                target_gate_crossing_count=target_crossing_count,
                target_gate_recovery_count=target_recovery_count,
                protected_regression_count=regression_count,
                protected_gate_crossing_count=crossing_count,
                goals=MappingProxyType(goal_reports),
                audit=MappingProxyType(
                    {
                        "whole_periodic_orbit_block": True,
                        "periodic_orbit_closed_caller_certified": True,
                        "individual_coordinate_ranking": False,
                        "global_adjoint_residual_partition": True,
                        "selection_score_semantics": (
                            "l2_of_positive_weighted_normalized_absolute_"
                            "error_improvements"
                        ),
                        "raw_dwr_magnitude_is_not_selection_score": True,
                    }
                ),
            )
        )

    for goal_row, goal in enumerate(goal_specs):
        orbit_sum = float(np.sum(normalized_matrix[goal_row, :]))
        expected = channel_results[goal.label].normalized_signed_correction
        scale = max(1.0, abs(orbit_sum), abs(expected))
        if abs(orbit_sum - expected) / scale > identity_tolerance:
            raise RuntimeError(
                f"{goal.label} whole-orbit DWR partition does not close"
            )

    ordered_orbits = sorted(
        orbit_results,
        key=lambda item: (
            item.protected_gate_crossing_count > 0,
            item.protected_regression_count > 0,
            item.target_gate_crossing_count > 0,
            item.target_regression_count > 0,
            -item.target_gate_recovery_count,
            -item.selection_score,
            item.target_regression_penalty,
            -item.target_net_absolute_error_improvement,
            item.orbit_id,
        ),
    )
    ranked_orbits = tuple(
        replace(result, rank=rank)
        for rank, result in enumerate(ordered_orbits, start=1)
    )

    singular_values = np.linalg.svd(
        normalized_matrix,
        compute_uv=False,
    )
    if singular_values.size:
        rank_tolerance = float(
            max(normalized_matrix.shape)
            * np.finfo(np.float64).eps
            * singular_values[0]
        )
        numerical_rank = int(
            np.count_nonzero(singular_values > rank_tolerance)
        )
    else:
        rank_tolerance = 0.0
        numerical_rank = 0
    _, rrqr_r, rrqr_pivots = qr(
        normalized_matrix,
        mode="economic",
        pivoting=True,
        check_finite=True,
    )
    rrqr_diagonal = np.abs(np.diag(rrqr_r))
    diagnostics = MappingProxyType(
        {
            "schema_version": "task035b.orbit-dwr-svd-rrqr.v1",
            "matrix_layout": "goal_rows_by_whole_orbit_columns",
            "goal_labels": labels,
            "orbit_ids": [orbit.orbit_id for orbit in orbit_blocks],
            "normalized_signed_dwr_matrix": normalized_matrix.tolist(),
            "singular_values": singular_values.tolist(),
            "numerical_rank": numerical_rank,
            "rank_tolerance": rank_tolerance,
            "rrqr_pivot_orbit_ids": [
                orbit_blocks[int(index)].orbit_id
                for index in rrqr_pivots
            ],
            "rrqr_diagonal_abs": rrqr_diagonal.tolist(),
            "svd_performed": True,
            "rrqr_performed": True,
            "rrqr_operates_on_whole_orbit_columns": True,
            "coordinate_axis_rrqr_performed": False,
        }
    )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.complement-schur-channel-dwr-analysis.v1"
            ),
            "status": "algebraic_kernel_pass_external_integration_not_run",
            "pass": True,
            "actual_algebraic_complement_dwr": True,
            "goal_count": len(goal_specs),
            "whole_orbit_count": len(orbit_blocks),
            "whole_orbit_partition_closes": True,
            "goal_roles_selection_target_and_protected_are_mutually_"
            "exclusive": True,
            "selection_targets_require_signed_baseline_error": True,
            "baseline_signed_error_convention": (
                "J_retained_minus_J_frozen_reference"
            ),
            "predicted_error_formula": (
                "baseline_signed_error_plus_orbit_DWR_correction"
            ),
            "orbit_ranking_policy": (
                "penalize protected and target regressions/gate crossings, "
                "then reward positive normalized absolute-error improvement"
            ),
            "full_p6_matrix_materialized_by_kernel": False,
            "Schur_matrix_materialized_by_kernel": False,
            "inactive_p6_rows_allocated_by_kernel": False,
            "ordinary_default_changed": False,
            "external_integration": {
                "mesh_integration": "not_run",
                "h14_integration": "not_run",
                "h14_mesh": "not_run",
                "dolfinx_mesh_entity_inventory": "not_run",
                "physical_p6_trace_basis_insertion": "not_run",
                "piola_riesz_pullback": "not_run",
                "periodic_orbit_numbering": "not_run",
                "floquet_pullback": "not_run",
                "DtN_port_integration": "not_run",
                "dtn_port_operator_and_goal_derivatives": "not_run",
                "inactive_row_integration": "not_run",
                "inactive_row_free_candidate_assembly": "not_run",
                "formal_12_channel_candidate": "not_run",
            },
            "physical_candidate_qualification_authorized": False,
            "external_integration_not_a_kernel_pass": True,
        }
    )
    return ComplementDWRAnalysis(
        primal_residual=primal_residual,
        complement_correction=correction,
        goals=MappingProxyType(channel_results),
        ranked_orbits=ranked_orbits,
        svd_rrqr_diagnostics=diagnostics,
        audit=audit,
    )


__all__ = [
    "ChannelDWRResult",
    "ChannelGoal",
    "ComplementDWRAnalysis",
    "ComplementSchurOperator",
    "GoalComponent",
    "OrbitDWRResult",
    "WholeOrbitBlock",
    "evaluate_complement_channel_dwr",
]
