"""Fail-closed six-cycle state machine for blind h/p decisions."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    GoalVector,
    normalized_goal_distance,
)
from .shadows import (
    HLevel3SaturationAuthority,
    P6SaturationAuthority,
    ShadowAction,
    ShadowCatalog,
    _replay_h_level3_saturation_authority_from_payload,
    _replay_p6_saturation_authority_from_payload,
    h_level3_saturation_authority_payload,
    p6_saturation_authority_payload,
)


INTERNAL_CERTIFICATE_SCHEMA = "task035e.blind-internal-certificate.v2"
STABILITY_REPEAT_VERIFICATION_SCHEMA = (
    "task035e.stability-repeat-verification.v1"
)


def _require_sha256(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _delta_packet_sha256(
    packet: tuple[tuple[str, float], ...],
) -> str:
    return _canonical_sha256(
        [[goal_id, float(value)] for goal_id, value in packet]
    )


def _delta_packets_close(
    left: tuple[tuple[str, float], ...],
    right: tuple[tuple[str, float], ...],
) -> bool:
    if tuple(row[0] for row in left) != FORMAL_GOAL_IDS:
        return False
    if tuple(row[0] for row in right) != FORMAL_GOAL_IDS:
        return False
    return all(
        math.isclose(
            float(left_value),
            float(right_value),
            rel_tol=1.0e-9,
            abs_tol=1.0e-15,
        )
        for (_, left_value), (_, right_value) in zip(
            left,
            right,
            strict=True,
        )
    )


def _both_safe_zero(left: float, right: float) -> bool:
    return abs(float(left)) <= 1.0e-30 and abs(float(right)) <= 1.0e-30


@dataclass(frozen=True, slots=True)
class StructuralInventory:
    """Current physically active algebraic/resource inventory."""

    active_dofs: int
    rows: int
    matrix_nnz: int
    factor_nnz: int
    solver_peak_bytes: int

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class ResourceEnvelope:
    """Hard Full3D limits used before accepting an action."""

    maximum_rows: int = 51_271
    maximum_matrix_nnz: int = 41_989_039
    maximum_factor_nnz: int = 212_343_991
    maximum_solver_peak_bytes: int = 11 * 1024**3

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

    def admits(
        self,
        current: StructuralInventory,
        action: ShadowAction,
    ) -> bool:
        return self.admits_combination(current, (action,))

    def admits_combination(
        self,
        current: StructuralInventory,
        actions: tuple[ShadowAction, ...],
    ) -> bool:
        projected = (
            current.rows + sum(row.cost.added_rows for row in actions),
            current.matrix_nnz
            + sum(row.cost.added_matrix_nnz for row in actions),
            current.factor_nnz
            + sum(row.cost.added_factor_nnz for row in actions),
            current.solver_peak_bytes
            + sum(row.cost.added_solver_peak_bytes for row in actions),
        )
        limits = (
            self.maximum_rows,
            self.maximum_matrix_nnz,
            self.maximum_factor_nnz,
            self.maximum_solver_peak_bytes,
        )
        return all(
            0 <= value <= limit
            for value, limit in zip(projected, limits, strict=True)
        )


@dataclass(frozen=True, slots=True)
class InternalGates:
    """All accuracy and discretization checks visible to the controller."""

    full_explicit_residual: float
    energy_closure_error: float
    absorption_volume: float
    floquet_residual_pass: bool
    hanging_residual_pass: bool
    serial_mpi_identity_pass: bool
    multilevel_mesh_pass: bool
    separated_patch_count: int
    all_local_levels_present: bool
    algebraic_budget_fraction: float
    dtn_budget_fraction: float
    postprocess_budget_fraction: float

    def __post_init__(self) -> None:
        for name in (
            "full_explicit_residual",
            "energy_closure_error",
            "absorption_volume",
            "algebraic_budget_fraction",
            "dtn_budget_fraction",
            "postprocess_budget_fraction",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            if value < 0.0:
                raise ValueError(f"{name} must be nonnegative")
            object.__setattr__(self, name, value)
        if (
            type(self.separated_patch_count) is not int
            or self.separated_patch_count < 0
        ):
            raise ValueError("separated_patch_count must be a nonnegative integer")
        for name in (
            "floquet_residual_pass",
            "hanging_residual_pass",
            "serial_mpi_identity_pass",
            "multilevel_mesh_pass",
            "all_local_levels_present",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")

    @property
    def passed(self) -> bool:
        return all(
            (
                self.full_explicit_residual <= 1.0e-9,
                abs(self.energy_closure_error) <= 1.0e-9,
                self.absorption_volume >= 0.0,
                self.floquet_residual_pass,
                self.hanging_residual_pass,
            )
        )

    @property
    def freeze_passed(self) -> bool:
        return all(
            (
                self.passed,
                self.serial_mpi_identity_pass,
                self.multilevel_mesh_pass,
                self.separated_patch_count >= 2,
                self.all_local_levels_present,
                self.algebraic_budget_fraction <= 0.10,
                self.dtn_budget_fraction <= 0.10,
                self.postprocess_budget_fraction <= 0.10,
            )
        )


@dataclass(frozen=True, slots=True)
class ShadowVerification:
    """Signed prediction-vs-actual check for an executed local action."""

    action_id: str
    action_sha256: str
    transition_action_sha256: str
    transition_action_file_sha256: str
    transition_action_identity_sha256: str
    next_mesh_forest_sha256: str
    next_degree_map_sha256: str
    next_plan_file_sha256: str
    next_plan_content_sha256: str
    next_state_sha256: str
    before_output_sha256: str
    after_output_sha256: str
    predicted_deltas: tuple[tuple[str, float], ...]
    actual_deltas: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.action_id, str) or not self.action_id:
            raise ValueError("action_id must be nonempty")
        for name in (
            "action_sha256",
            "transition_action_sha256",
            "transition_action_file_sha256",
            "transition_action_identity_sha256",
            "next_mesh_forest_sha256",
            "next_degree_map_sha256",
            "next_plan_file_sha256",
            "next_plan_content_sha256",
            "next_state_sha256",
            "before_output_sha256",
            "after_output_sha256",
        ):
            _require_sha256(getattr(self, name), label=name)
        for name in ("predicted_deltas", "actual_deltas"):
            packet = getattr(self, name)
            if tuple(row[0] for row in packet) != FORMAL_GOAL_IDS:
                raise ValueError(
                    f"{name} must list all formal goals in canonical order"
                )
            for goal_id, value in packet:
                if not math.isfinite(float(value)):
                    raise ValueError(f"{name}[{goal_id}] must be finite")

    @property
    def predicted_delta_sha256(self) -> str:
        return _delta_packet_sha256(self.predicted_deltas)

    @property
    def effectivities(self) -> tuple[tuple[str, float | None], ...]:
        predicted = dict(self.predicted_deltas)
        result: list[tuple[str, float | None]] = []
        for goal_id, actual in self.actual_deltas:
            estimate = predicted[goal_id]
            if _both_safe_zero(estimate, actual):
                result.append((goal_id, None))
            elif abs(float(actual)) <= 1.0e-30:
                result.append((goal_id, math.inf))
            else:
                result.append((goal_id, float(estimate) / float(actual)))
        return tuple(result)

    @property
    def within_factor_two_fraction(self) -> float:
        count = sum(
            value is None
            or (
                value is not None
                and math.isfinite(value)
                and 0.5 <= abs(float(value)) <= 2.0
            )
            for goal_id, value in self.effectivities
        )
        return count / len(FORMAL_GOAL_IDS)

    @property
    def passed(self) -> bool:
        return all(
            value is None or (math.isfinite(value) and value >= 0.0)
            for _, value in self.effectivities
        ) and self.within_factor_two_fraction >= 0.90

    def validates_transition(
        self,
        *,
        expected_action_sha256: str,
        expected_transition_action_sha256: str,
        expected_transition_action_file_sha256: str,
        expected_transition_action_identity_sha256: str,
        expected_next_mesh_forest_sha256: str,
        expected_next_degree_map_sha256: str,
        expected_next_plan_file_sha256: str,
        expected_next_plan_content_sha256: str,
        expected_next_state_sha256: str,
        expected_predicted_delta_sha256: str,
        expected_before_output_sha256: str,
        expected_after_output_sha256: str,
        expected_actual_deltas: tuple[tuple[str, float], ...],
    ) -> bool:
        """Bind verification to one selected action and solved transition."""

        return (
            self.action_sha256 == expected_action_sha256
            and self.transition_action_sha256
            == expected_transition_action_sha256
            and self.transition_action_file_sha256
            == expected_transition_action_file_sha256
            and self.transition_action_identity_sha256
            == expected_transition_action_identity_sha256
            and self.next_mesh_forest_sha256
            == expected_next_mesh_forest_sha256
            and self.next_degree_map_sha256
            == expected_next_degree_map_sha256
            and self.next_plan_file_sha256
            == expected_next_plan_file_sha256
            and self.next_plan_content_sha256
            == expected_next_plan_content_sha256
            and self.next_state_sha256 == expected_next_state_sha256
            and self.predicted_delta_sha256
            == expected_predicted_delta_sha256
            and self.before_output_sha256 == expected_before_output_sha256
            and self.after_output_sha256 == expected_after_output_sha256
            and _delta_packets_close(
                self.actual_deltas,
                expected_actual_deltas,
            )
        )


@dataclass(frozen=True, slots=True)
class StabilityRepeatVerification:
    """Identity-only proof for one solved ``p-keep`` stability repeat.

    Unlike :class:`ShadowVerification`, a stability repeat has no estimated
    delta or effectivity.  It proves that the solver was run again on exactly
    the same numerical space while every immutable execution artifact moved
    forward to a fresh cycle.
    """

    action_id: str
    action_kind: str
    action_sha256: str
    action_file_sha256: str
    action_identity_sha256: str
    from_state_sha256: str
    next_state_sha256: str
    previous_plan_file_sha256: str
    previous_plan_content_sha256: str
    previous_plan_solver_content_sha256: str
    next_plan_file_sha256: str
    next_plan_content_sha256: str
    next_plan_solver_content_sha256: str
    previous_mesh_forest_sha256: str
    next_mesh_forest_sha256: str
    previous_degree_map_sha256: str
    next_degree_map_sha256: str
    before_solution_snapshot_sha256: str
    after_solution_snapshot_sha256: str
    before_watchdog_record_file_sha256: str
    after_watchdog_record_file_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.action_id, str) or not self.action_id:
            raise ValueError("stability-repeat action_id must be nonempty")
        if self.action_kind != "p-keep":
            raise ValueError("stability repeat must use a p-keep action")
        for name in (
            "action_sha256",
            "action_file_sha256",
            "action_identity_sha256",
            "from_state_sha256",
            "next_state_sha256",
            "previous_plan_file_sha256",
            "previous_plan_content_sha256",
            "previous_plan_solver_content_sha256",
            "next_plan_file_sha256",
            "next_plan_content_sha256",
            "next_plan_solver_content_sha256",
            "previous_mesh_forest_sha256",
            "next_mesh_forest_sha256",
            "previous_degree_map_sha256",
            "next_degree_map_sha256",
            "before_solution_snapshot_sha256",
            "after_solution_snapshot_sha256",
            "before_watchdog_record_file_sha256",
            "after_watchdog_record_file_sha256",
        ):
            _require_sha256(getattr(self, name), label=name)
        if (
            self.previous_mesh_forest_sha256
            != self.next_mesh_forest_sha256
            or self.previous_degree_map_sha256
            != self.next_degree_map_sha256
            or self.previous_plan_solver_content_sha256
            != self.next_plan_solver_content_sha256
        ):
            raise ValueError(
                "p-keep changed mesh, degree, or canonical solver content"
            )
        for before_name, after_name in (
            ("from_state_sha256", "next_state_sha256"),
            ("previous_plan_file_sha256", "next_plan_file_sha256"),
            ("previous_plan_content_sha256", "next_plan_content_sha256"),
            (
                "before_solution_snapshot_sha256",
                "after_solution_snapshot_sha256",
            ),
            (
                "before_watchdog_record_file_sha256",
                "after_watchdog_record_file_sha256",
            ),
        ):
            if getattr(self, before_name) == getattr(self, after_name):
                raise ValueError(
                    "p-keep stability repeat reused an immutable "
                    f"execution identity at {before_name}"
                )

    @property
    def verification_sha256(self) -> str:
        """Canonical self-hash of the closed verification payload."""

        return _canonical_sha256(
            _stability_repeat_unsigned_payload(self)
        )

    def validates_transition(
        self,
        *,
        previous_result: BlindCycleResult,
        current_cycle: BlindCycleInput,
    ) -> bool:
        """Bind the repeat to adjacent cycle results without goal data."""

        return (
            self.from_state_sha256 == previous_result.state_sha256
            and self.next_state_sha256 == current_cycle.state_sha256
            and self.previous_plan_file_sha256
            == previous_result.plan_file_sha256
            and self.previous_plan_content_sha256
            == previous_result.plan_content_sha256
            and self.previous_plan_solver_content_sha256
            == previous_result.plan_solver_content_sha256
            and self.next_plan_file_sha256
            == current_cycle.plan_file_sha256
            and self.next_plan_content_sha256
            == current_cycle.plan_content_sha256
            and self.next_plan_solver_content_sha256
            == current_cycle.plan_solver_content_sha256
            and self.previous_mesh_forest_sha256
            == previous_result.mesh_forest_sha256
            and self.next_mesh_forest_sha256
            == current_cycle.mesh_forest_sha256
            and self.previous_degree_map_sha256
            == previous_result.degree_map_sha256
            and self.next_degree_map_sha256
            == current_cycle.degree_map_sha256
            and self.before_solution_snapshot_sha256
            == previous_result.solution_snapshot_sha256
            and self.after_solution_snapshot_sha256
            == current_cycle.solution_snapshot_sha256
            and self.before_watchdog_record_file_sha256
            == previous_result.watchdog_record_file_sha256
            and self.after_watchdog_record_file_sha256
            == current_cycle.watchdog_record_file_sha256
        )


_STABILITY_REPEAT_VERIFICATION_KEYS = frozenset(
    {
        "schema_version",
        "action_id",
        "action_kind",
        "action_sha256",
        "action_file_sha256",
        "action_identity_sha256",
        "from_state_sha256",
        "next_state_sha256",
        "previous_plan_file_sha256",
        "previous_plan_content_sha256",
        "previous_plan_solver_content_sha256",
        "next_plan_file_sha256",
        "next_plan_content_sha256",
        "next_plan_solver_content_sha256",
        "previous_mesh_forest_sha256",
        "next_mesh_forest_sha256",
        "previous_degree_map_sha256",
        "next_degree_map_sha256",
        "before_solution_snapshot_sha256",
        "after_solution_snapshot_sha256",
        "before_watchdog_record_file_sha256",
        "after_watchdog_record_file_sha256",
        "verification_sha256",
    }
)


def _stability_repeat_unsigned_payload(
    verification: StabilityRepeatVerification,
) -> dict[str, Any]:
    return {
        "schema_version": STABILITY_REPEAT_VERIFICATION_SCHEMA,
        **{
            name: getattr(verification, name)
            for name in StabilityRepeatVerification.__dataclass_fields__
        },
    }


def stability_repeat_verification_payload(
    verification: StabilityRepeatVerification,
) -> dict[str, Any]:
    """Serialize one stability repeat using its closed, self-hashed schema."""

    unsigned = _stability_repeat_unsigned_payload(verification)
    return {
        **unsigned,
        "verification_sha256": _canonical_sha256(unsigned),
    }


def stability_repeat_verification_from_payload(
    payload: Mapping[str, Any],
) -> StabilityRepeatVerification:
    """Rebuild and independently validate one serialized repeat proof."""

    if not isinstance(payload, Mapping) or set(payload) != set(
        _STABILITY_REPEAT_VERIFICATION_KEYS
    ):
        raise ValueError(
            "stability-repeat verification must use its closed schema"
        )
    if payload["schema_version"] != STABILITY_REPEAT_VERIFICATION_SCHEMA:
        raise ValueError("unsupported stability-repeat verification schema")
    stored_sha = _require_sha256(
        payload["verification_sha256"],
        label="stability-repeat verification SHA-256",
    )
    unsigned = {
        name: payload[name]
        for name in payload
        if name != "verification_sha256"
    }
    if _canonical_sha256(unsigned) != stored_sha:
        raise ValueError("stability-repeat verification self-hash differs")
    verification = StabilityRepeatVerification(
        **{
            name: payload[name]
            for name in StabilityRepeatVerification.__dataclass_fields__
        }
    )
    if verification.verification_sha256 != stored_sha:
        raise ValueError("stability-repeat verification replay hash differs")
    return verification


@dataclass(frozen=True, slots=True)
class BlindCycleInput:
    """One solved state and its current-state estimates."""

    cycle_index: int
    mesh_forest_sha256: str
    degree_map_sha256: str
    plan_file_sha256: str
    plan_content_sha256: str
    plan_solver_content_sha256: str
    state_sha256: str
    solution_snapshot_sha256: str
    watchdog_record_file_sha256: str
    complete_output_sha256: str
    full_residual_sha256: str
    adjoint_bundle_sha256: str
    resource_inventory_sha256: str
    goals: GoalVector
    shadows: ShadowCatalog
    inventory: StructuralInventory
    gates: InternalGates
    executed_action_verifications: tuple[ShadowVerification, ...] = ()
    stability_repeat_verification: StabilityRepeatVerification | None = None

    def __post_init__(self) -> None:
        if type(self.cycle_index) is not int or not 0 <= self.cycle_index <= 5:
            raise ValueError("cycle_index must be in [0, 5]")
        for name in (
            "mesh_forest_sha256",
            "degree_map_sha256",
            "plan_file_sha256",
            "plan_content_sha256",
            "plan_solver_content_sha256",
            "state_sha256",
            "solution_snapshot_sha256",
            "watchdog_record_file_sha256",
            "complete_output_sha256",
            "full_residual_sha256",
            "adjoint_bundle_sha256",
            "resource_inventory_sha256",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError(f"{name} must be a lowercase SHA-256")
        if self.shadows.current_goal_sha256 != self.goals.sha256:
            raise ValueError("shadow catalog does not match the current goals")
        saturation = self.shadows.p6_saturation
        if (
            saturation.current_plan_file_sha256 != self.plan_file_sha256
            or saturation.current_mesh_forest_sha256
            != self.mesh_forest_sha256
            or saturation.current_degree_map_sha256
            != self.degree_map_sha256
        ):
            raise ValueError(
                "p6 saturation authority does not match the current "
                "plan/forest/degree identities"
            )
        h_saturation = self.shadows.h_level3_saturation
        if (
            h_saturation.current_plan_file_sha256
            != self.plan_file_sha256
            or h_saturation.current_mesh_forest_sha256
            != self.mesh_forest_sha256
            or h_saturation.current_degree_map_sha256
            != self.degree_map_sha256
        ):
            raise ValueError(
                "level3 h-saturation authority does not match the current "
                "plan/forest/degree identities"
            )


@dataclass(frozen=True, slots=True)
class BlindCycleResult:
    """Fail-closed decision emitted after one current solve."""

    cycle_index: int
    accepted_current_state: bool
    status: str
    reasons: tuple[str, ...]
    selected_action_ids: tuple[str, ...]
    selected_action_bindings: tuple[
        tuple[str, str, str, str, str, str, str, str],
        ...,
    ]
    p_shadow_maximum: float
    h_shadow_maximum: float
    p_enrichment_action_count: int
    h_enrichment_action_count: int
    stable_from_previous: bool
    stable_streak: int
    freeze_ready: bool
    goals: GoalVector
    mesh_forest_sha256: str
    degree_map_sha256: str
    plan_file_sha256: str
    plan_content_sha256: str
    plan_solver_content_sha256: str
    state_sha256: str
    solution_snapshot_sha256: str
    watchdog_record_file_sha256: str
    complete_output_sha256: str
    full_residual_sha256: str
    adjoint_bundle_sha256: str
    shadow_catalog_sha256: str
    p6_saturation: P6SaturationAuthority
    h_level3_saturation: HLevel3SaturationAuthority
    executed_verification_sha256: str
    stability_repeat_verification: StabilityRepeatVerification | None
    stability_repeat_verification_sha256: str
    internal_certificate: Mapping[str, Any]
    internal_certificate_sha256: str
    resource_inventory_sha256: str
    p_shadow_signed_dwr_maximum: float | None = None
    p_shadow_endpoint_maximum: float | None = None
    h_shadow_signed_dwr_maximum: float | None = None
    h_shadow_endpoint_maximum: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.p6_saturation, P6SaturationAuthority):
            raise ValueError(
                "blind result requires closed p6 saturation authority"
            )
        if not isinstance(
            self.h_level3_saturation,
            HLevel3SaturationAuthority,
        ):
            raise ValueError(
                "blind result requires closed level3 h-saturation authority"
            )
        if self.selected_action_ids != tuple(
            row[0] for row in self.selected_action_bindings
        ):
            raise ValueError(
                "selected action IDs differ from their content bindings"
            )
        if len(self.selected_action_bindings) > 1:
            raise ValueError(
                "a blind cycle may select at most one independent lane"
            )
        expected_repeat_sha = (
            _canonical_sha256(None)
            if self.stability_repeat_verification is None
            else self.stability_repeat_verification.verification_sha256
        )
        if self.stability_repeat_verification_sha256 != expected_repeat_sha:
            raise ValueError("stability-repeat verification SHA-256 mismatch")
        separate_maxima = (
            self.p_shadow_signed_dwr_maximum,
            self.p_shadow_endpoint_maximum,
            self.h_shadow_signed_dwr_maximum,
            self.h_shadow_endpoint_maximum,
        )
        if any(value is not None for value in separate_maxima):
            if any(value is None for value in separate_maxima):
                raise ValueError(
                    "separate shadow maxima must be reported as one complete set"
                )
            numeric = tuple(float(value) for value in separate_maxima)
            if any(
                not math.isfinite(value) or value < 0.0
                for value in numeric
            ):
                raise ValueError(
                    "separate shadow maxima must be finite and nonnegative"
                )
            if not math.isclose(
                self.p_shadow_maximum,
                max(numeric[0], numeric[1]),
                rel_tol=0.0,
                abs_tol=1.0e-15,
            ):
                raise ValueError(
                    "p shadow decision maximum differs from its two sources"
                )
            if not math.isclose(
                self.h_shadow_maximum,
                max(numeric[2], numeric[3]),
                rel_tol=0.0,
                abs_tol=1.0e-15,
            ):
                raise ValueError(
                    "h shadow decision maximum differs from its two sources"
                )
        validate_internal_certificate_payload(
            self.internal_certificate,
            expected_result=self,
        )
        if _canonical_sha256(dict(self.internal_certificate)) != (
            self.internal_certificate_sha256
        ):
            raise ValueError("internal certificate SHA-256 mismatch")


@dataclass(frozen=True, slots=True)
class BlindTrial:
    """Immutable state of one independent initial-path trial."""

    trial_id: str
    algorithm_id: str
    source_sha: str
    initial_path_id: str
    initial_mesh_forest_sha256: str
    physical_identity_sha256: str
    maximum_cycles: int = 6
    results: tuple[BlindCycleResult, ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= int(self.maximum_cycles) <= 6:
            raise ValueError("maximum_cycles must be in [1, 6]")
        if len(self.results) > self.maximum_cycles:
            raise ValueError("trial contains too many cycle results")
        if tuple(row.cycle_index for row in self.results) != tuple(
            range(len(self.results))
        ):
            raise ValueError("trial cycle indices are not contiguous")
        if (
            len(self.source_sha) not in {40, 64}
            or any(
                character not in "0123456789abcdef"
                for character in self.source_sha
            )
        ):
            raise ValueError("source_sha is invalid")
        _require_sha256(
            self.initial_mesh_forest_sha256,
            label="initial_mesh_forest_sha256",
        )
        _require_sha256(
            self.physical_identity_sha256,
            label="physical_identity_sha256",
        )
        for name in ("trial_id", "algorithm_id", "initial_path_id"):
            if not isinstance(getattr(self, name), str) or not getattr(
                self,
                name,
            ):
                raise ValueError(f"{name} must be nonempty")

    @property
    def last_accepted(self) -> BlindCycleResult | None:
        return next(
            (
                row
                for row in reversed(self.results)
                if row.accepted_current_state
            ),
            None,
        )

    @property
    def cycle_chain_root_sha256(self) -> str:
        return _canonical_sha256(
            {
                "schema_version": "task035e.blind-cycle-chain.v1",
                "result_certificate_sha256": [
                    row.internal_certificate_sha256 for row in self.results
                ],
            }
        )


_INTERNAL_CERTIFICATE_KEYS = frozenset(
    {
        "schema_version",
        "cycle_index",
        "accepted_current_state",
        "status",
        "reasons",
        "selected_action_bindings",
        "p_shadow_maximum",
        "h_shadow_maximum",
        "p_enrichment_action_count",
        "h_enrichment_action_count",
        "stable_from_previous",
        "stable_streak",
        "freeze_ready",
        "formal_goal_count",
        "formal_goal_inventory_sha256",
        "goal_sha256",
        "mesh_forest_sha256",
        "degree_map_sha256",
        "plan_file_sha256",
        "plan_content_sha256",
        "plan_solver_content_sha256",
        "state_sha256",
        "solution_snapshot_sha256",
        "watchdog_record_file_sha256",
        "complete_output_sha256",
        "full_residual_sha256",
        "adjoint_bundle_sha256",
        "shadow_catalog_sha256",
        "p6_saturation",
        "h_level3_saturation",
        "executed_verification_sha256",
        "stability_repeat_verification",
        "stability_repeat_verification_sha256",
        "resource_inventory_sha256",
        "gates",
    }
)
_INTERNAL_GATE_KEYS = frozenset(InternalGates.__dataclass_fields__)


def _internal_gates_payload(gates: InternalGates) -> dict[str, Any]:
    return {
        name: getattr(gates, name)
        for name in InternalGates.__dataclass_fields__
    }


def _certificate_freeze_gate(payload: Mapping[str, Any]) -> bool:
    gates = InternalGates(**dict(payload["gates"]))
    saturation = _replay_p6_saturation_authority_from_payload(
        payload["p6_saturation"]
    )
    h_saturation = _replay_h_level3_saturation_authority_from_payload(
        payload["h_level3_saturation"]
    )
    p_lane_is_covered = (
        int(payload["p_enrichment_action_count"]) >= 1
        or (
            saturation.p6_target_count >= 1
            and saturation.freeze_passed
        )
    )
    h_lane_is_covered = (
        int(payload["h_enrichment_action_count"]) >= 1
        or (
            h_saturation.level_two_target_count >= 1
            and h_saturation.freeze_passed
        )
    )
    maximum_level_targets_are_covered = (
        h_saturation.level_two_target_count == 0
        or h_saturation.freeze_passed
    )
    return all(
        (
            payload["accepted_current_state"] is True,
            payload["status"] == "freeze_ready",
            not payload["selected_action_bindings"],
            float(payload["p_shadow_maximum"]) <= 0.5,
            float(payload["h_shadow_maximum"]) <= 0.5,
            p_lane_is_covered,
            h_lane_is_covered,
            maximum_level_targets_are_covered,
            int(payload["stable_streak"]) >= 2,
            gates.freeze_passed,
            saturation.freeze_passed,
        )
    )


def validate_internal_certificate_payload(
    payload: Mapping[str, Any],
    *,
    expected_result: BlindCycleResult | None = None,
) -> None:
    """Validate one closed F1--F5 certificate independently of a bool claim."""

    if not isinstance(payload, Mapping) or set(payload) != set(
        _INTERNAL_CERTIFICATE_KEYS
    ):
        raise ValueError("internal certificate must use the closed Task035e schema")
    if payload["schema_version"] != INTERNAL_CERTIFICATE_SCHEMA:
        raise ValueError("unsupported internal certificate schema")
    if type(payload["cycle_index"]) is not int or not 0 <= int(
        payload["cycle_index"]
    ) <= 5:
        raise ValueError("internal certificate cycle_index is invalid")
    for name in (
        "accepted_current_state",
        "stable_from_previous",
        "freeze_ready",
    ):
        if type(payload[name]) is not bool:
            raise ValueError(f"internal certificate {name} must be boolean")
    if not isinstance(payload["status"], str):
        raise ValueError("internal certificate status must be a string")
    if (
        not isinstance(payload["reasons"], list)
        or any(not isinstance(value, str) for value in payload["reasons"])
    ):
        raise ValueError("internal certificate reasons must be strings")
    bindings = payload["selected_action_bindings"]
    if not isinstance(bindings, list):
        raise ValueError("selected_action_bindings must be an array")
    for index, binding in enumerate(bindings):
        if (
            not isinstance(binding, list)
            or len(binding) != 8
            or not isinstance(binding[0], str)
            or not binding[0]
        ):
            raise ValueError(f"selected action binding {index} is invalid")
        _require_sha256(binding[1], label="selected action SHA-256")
        _require_sha256(binding[2], label="selected DWR packet SHA-256")
        _require_sha256(
            binding[3],
            label="selected transition action SHA-256",
        )
        _require_sha256(
            binding[4],
            label="selected transition action file SHA-256",
        )
        _require_sha256(
            binding[5],
            label="selected transition action identity SHA-256",
        )
        _require_sha256(
            binding[6],
            label="selected next mesh forest SHA-256",
        )
        _require_sha256(
            binding[7],
            label="selected next degree map SHA-256",
        )
    if len({row[0] for row in bindings}) != len(bindings):
        raise ValueError("selected action bindings must be unique")
    if len(bindings) > 1:
        raise ValueError(
            "internal certificate selects more than one independent lane"
        )
    for name in ("p_shadow_maximum", "h_shadow_maximum"):
        value = float(payload[name])
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"internal certificate {name} must be nonnegative")
    for name in (
        "p_enrichment_action_count",
        "h_enrichment_action_count",
        "stable_streak",
    ):
        if type(payload[name]) is not int or int(payload[name]) < 0:
            raise ValueError(f"internal certificate {name} must be nonnegative")
    if payload["formal_goal_count"] != len(FORMAL_GOAL_IDS):
        raise ValueError("internal certificate formal goal count is incomplete")
    if (
        payload["formal_goal_inventory_sha256"]
        != FORMAL_GOAL_INVENTORY_SHA256
    ):
        raise ValueError("internal certificate formal goal inventory differs")
    for name in (
        "formal_goal_inventory_sha256",
        "goal_sha256",
        "mesh_forest_sha256",
        "degree_map_sha256",
        "plan_file_sha256",
        "plan_content_sha256",
        "plan_solver_content_sha256",
        "state_sha256",
        "solution_snapshot_sha256",
        "watchdog_record_file_sha256",
        "complete_output_sha256",
        "full_residual_sha256",
        "adjoint_bundle_sha256",
        "shadow_catalog_sha256",
        "executed_verification_sha256",
        "stability_repeat_verification_sha256",
        "resource_inventory_sha256",
    ):
        _require_sha256(payload[name], label=name)
    _replay_p6_saturation_authority_from_payload(
        payload["p6_saturation"]
    )
    _replay_h_level3_saturation_authority_from_payload(
        payload["h_level3_saturation"]
    )
    repeat_payload = payload["stability_repeat_verification"]
    repeat = (
        None
        if repeat_payload is None
        else stability_repeat_verification_from_payload(
            repeat_payload
        )
    )
    expected_repeat_sha = (
        _canonical_sha256(None)
        if repeat is None
        else repeat.verification_sha256
    )
    if payload["stability_repeat_verification_sha256"] != expected_repeat_sha:
        raise ValueError(
            "internal certificate stability-repeat SHA-256 differs"
        )
    if not isinstance(payload["gates"], Mapping) or set(payload["gates"]) != set(
        _INTERNAL_GATE_KEYS
    ):
        raise ValueError("internal certificate gates use an open or incomplete schema")
    InternalGates(**dict(payload["gates"]))
    recomputed_freeze = _certificate_freeze_gate(payload)
    if payload["freeze_ready"] is not recomputed_freeze:
        raise ValueError("internal certificate freeze_ready is not recomputable")
    if expected_result is None:
        return
    expected = {
        "cycle_index": expected_result.cycle_index,
        "accepted_current_state": expected_result.accepted_current_state,
        "status": expected_result.status,
        "reasons": list(expected_result.reasons),
        "selected_action_bindings": [
            list(row) for row in expected_result.selected_action_bindings
        ],
        "p_shadow_maximum": expected_result.p_shadow_maximum,
        "h_shadow_maximum": expected_result.h_shadow_maximum,
        "p_enrichment_action_count": expected_result.p_enrichment_action_count,
        "h_enrichment_action_count": expected_result.h_enrichment_action_count,
        "stable_from_previous": expected_result.stable_from_previous,
        "stable_streak": expected_result.stable_streak,
        "freeze_ready": expected_result.freeze_ready,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "goal_sha256": expected_result.goals.sha256,
        "mesh_forest_sha256": expected_result.mesh_forest_sha256,
        "degree_map_sha256": expected_result.degree_map_sha256,
        "plan_file_sha256": expected_result.plan_file_sha256,
        "plan_content_sha256": expected_result.plan_content_sha256,
        "plan_solver_content_sha256": (
            expected_result.plan_solver_content_sha256
        ),
        "state_sha256": expected_result.state_sha256,
        "solution_snapshot_sha256": expected_result.solution_snapshot_sha256,
        "watchdog_record_file_sha256": (
            expected_result.watchdog_record_file_sha256
        ),
        "complete_output_sha256": expected_result.complete_output_sha256,
        "full_residual_sha256": expected_result.full_residual_sha256,
        "adjoint_bundle_sha256": expected_result.adjoint_bundle_sha256,
        "shadow_catalog_sha256": expected_result.shadow_catalog_sha256,
        "p6_saturation": p6_saturation_authority_payload(
            expected_result.p6_saturation
        ),
        "h_level3_saturation": h_level3_saturation_authority_payload(
            expected_result.h_level3_saturation
        ),
        "executed_verification_sha256": (
            expected_result.executed_verification_sha256
        ),
        "stability_repeat_verification": (
            None
            if expected_result.stability_repeat_verification is None
            else stability_repeat_verification_payload(
                expected_result.stability_repeat_verification
            )
        ),
        "stability_repeat_verification_sha256": (
            expected_result.stability_repeat_verification_sha256
        ),
        "resource_inventory_sha256": expected_result.resource_inventory_sha256,
    }
    for name, value in expected.items():
        if payload[name] != value:
            raise ValueError(f"internal certificate differs at {name}")


def _best_action(
    actions: tuple[ShadowAction, ...],
    *,
    inventory: StructuralInventory,
    envelope: ResourceEnvelope,
) -> ShadowAction | None:
    eligible = tuple(
        row
        for row in actions
        if row.sign_consistent
        and envelope.admits(inventory, row)
    )
    return max(eligible, key=_action_rank, default=None)


def _action_rank(action: ShadowAction) -> tuple[float, float, float, float, str]:
    """Established deterministic benefit/cost ordering across either lane."""

    return (
        action.benefit_per_cost("solver_peak"),
        action.benefit_per_cost("factor_nnz"),
        action.benefit_per_cost("matrix_nnz"),
        action.benefit_per_cost("rows"),
        action.action_id,
    )


def _select_actions(
    cycle: BlindCycleInput,
    *,
    envelope: ResourceEnvelope,
    coarsening_allowed: bool,
) -> tuple[tuple[ShadowAction, ...], tuple[str, ...]]:
    reasons: list[str] = []
    p_strong = cycle.shadows.maximum_normalized_delta("p") > 0.5
    h_strong = cycle.shadows.maximum_normalized_delta("h") > 0.5
    p_best = _best_action(
        tuple(row for row in cycle.shadows.p_actions if row.kind == "p-up"),
        inventory=cycle.inventory,
        envelope=envelope,
    )
    h_best = _best_action(
        tuple(row for row in cycle.shadows.h_actions if row.kind == "h-refine"),
        inventory=cycle.inventory,
        envelope=envelope,
    )
    if p_strong and p_best is None:
        reasons.append("p_lane_has_no_sign_consistent_action_inside_resource_envelope")
    if h_strong and h_best is None:
        reasons.append("h_lane_has_no_sign_consistent_action_inside_resource_envelope")
    enrichment_candidates = tuple(
        row
        for strong, row in ((p_strong, p_best), (h_strong, h_best))
        if strong and row is not None
    )
    selected: list[ShadowAction] = []
    if enrichment_candidates:
        selected.append(max(enrichment_candidates, key=_action_rank))
        if len(enrichment_candidates) == 2:
            reasons.append(
                "single_lane_policy_without_combined_shadow_selected_"
                f"{'p' if selected[0].kind == 'p-up' else 'h'}"
            )
    if not p_strong and not h_strong and coarsening_allowed:
        p_down = _best_action(
            tuple(
                row
                for row in cycle.shadows.p_actions
                if row.kind == "p-down"
            ),
            inventory=cycle.inventory,
            envelope=envelope,
        )
        h_down = _best_action(
            tuple(
                row
                for row in cycle.shadows.h_actions
                if row.kind == "h-coarsen"
            ),
            inventory=cycle.inventory,
            envelope=envelope,
        )
        coarsening_candidates = tuple(
            row for row in (p_down, h_down) if row is not None
        )
        if coarsening_candidates:
            selected.append(max(coarsening_candidates, key=_action_rank))
            if len(coarsening_candidates) == 2:
                reasons.append(
                    "single_lane_policy_without_combined_shadow_selected_"
                    f"{'p' if selected[0].kind == 'p-down' else 'h'}"
                )
    if (
        not p_strong
        and not h_strong
        and not selected
        and cycle.shadows.p6_saturation.freeze_passed
        and (
            cycle.shadows.h_level3_saturation.level_two_target_count
            == 0
            or cycle.shadows.h_level3_saturation.freeze_passed
        )
    ):
        reasons.append("both_shadow_lanes_inside_freeze_threshold")
    return tuple(selected), tuple(reasons)


def advance_blind_trial(
    trial: BlindTrial,
    cycle: BlindCycleInput,
    *,
    envelope: ResourceEnvelope = ResourceEnvelope(),
) -> BlindTrial:
    """Accept/reject a solved state and choose the next local action."""

    expected_index = len(trial.results)
    if cycle.cycle_index != expected_index:
        raise ValueError(
            f"expected cycle {expected_index}, got {cycle.cycle_index}"
        )
    if expected_index >= trial.maximum_cycles:
        raise ValueError("blind trial has reached its cycle limit")
    reasons: list[str] = []
    accepted = True
    if not cycle.gates.passed:
        accepted = False
        reasons.append("current_internal_gate_failed")
    if not envelope.admits_combination(cycle.inventory, ()):
        accepted = False
        reasons.append("current_inventory_exceeds_resource_envelope")
    sign_conflict_action_ids = tuple(
        sorted(
            row.action_id
            for row in (
                *cycle.shadows.p_actions,
                *cycle.shadows.h_actions,
            )
            if not row.sign_consistent
        )
    )
    if sign_conflict_action_ids:
        accepted = False
        reasons.append("shadow_dwr_endpoint_sign_conflict")
        reasons.extend(
            f"rejected_shadow_action:{action_id}"
            for action_id in sign_conflict_action_ids
        )
    previous_result = trial.results[-1] if trial.results else None
    expected_bindings = (
        {
            row[0]: row[1:]
            for row in previous_result.selected_action_bindings
        }
        if previous_result is not None
        else {}
    )
    actual_verifications = {
        row.action_id: row for row in cycle.executed_action_verifications
    }
    repeat = cycle.stability_repeat_verification
    if len(actual_verifications) != len(cycle.executed_action_verifications):
        accepted = False
        reasons.append("executed_action_verification_ids_are_not_unique")
    if actual_verifications and repeat is not None:
        accepted = False
        reasons.append("stability_repeat_and_shadow_verification_role_mixed")
    if previous_result is None:
        if actual_verifications:
            accepted = False
            reasons.append("executed_action_verification_inventory_mismatch")
        if repeat is not None:
            accepted = False
            reasons.append("cycle_zero_stability_repeat_is_forbidden")
    elif expected_bindings:
        if repeat is not None:
            accepted = False
            reasons.append(
                "selected_action_cannot_use_stability_repeat_verification"
            )
        if set(actual_verifications) != set(expected_bindings):
            accepted = False
            reasons.append("executed_action_verification_inventory_mismatch")
        previous_goals = previous_result.goals.by_id
        current_goals = cycle.goals.by_id
        expected_actual_deltas = tuple(
            (
                goal_id,
                current_goals[goal_id] - previous_goals[goal_id],
            )
            for goal_id in FORMAL_GOAL_IDS
        )
        for action_id, verification in actual_verifications.items():
            (
                action_sha,
                delta_sha,
                transition_action_sha,
                transition_action_file_sha,
                transition_action_identity_sha,
                next_mesh_forest_sha,
                next_degree_map_sha,
            ) = expected_bindings[action_id]
            if not verification.validates_transition(
                expected_action_sha256=action_sha,
                expected_transition_action_sha256=transition_action_sha,
                expected_transition_action_file_sha256=(
                    transition_action_file_sha
                ),
                expected_transition_action_identity_sha256=(
                    transition_action_identity_sha
                ),
                expected_next_mesh_forest_sha256=cycle.mesh_forest_sha256,
                expected_next_degree_map_sha256=cycle.degree_map_sha256,
                expected_next_plan_file_sha256=cycle.plan_file_sha256,
                expected_next_plan_content_sha256=(
                    cycle.plan_content_sha256
                ),
                expected_next_state_sha256=cycle.state_sha256,
                expected_predicted_delta_sha256=delta_sha,
                expected_before_output_sha256=(
                    previous_result.complete_output_sha256
                ),
                expected_after_output_sha256=cycle.complete_output_sha256,
                expected_actual_deltas=expected_actual_deltas,
            ):
                accepted = False
                reasons.append("executed_action_verification_binding_failed")
                break
            if not verification.passed:
                accepted = False
                reasons.append("executed_action_verification_failed")
                break
            if (
                next_mesh_forest_sha != cycle.mesh_forest_sha256
                or next_degree_map_sha != cycle.degree_map_sha256
            ):
                accepted = False
                reasons.append(
                    "executed_action_next_plan_identity_failed"
                )
                break
    else:
        if actual_verifications:
            accepted = False
            reasons.append("executed_action_verification_inventory_mismatch")
        repeat_required = (
            previous_result.accepted_current_state
            and not previous_result.freeze_ready
        )
        if repeat_required and repeat is None:
            accepted = False
            reasons.append("stability_repeat_verification_missing")
        elif not repeat_required and repeat is not None:
            accepted = False
            reasons.append("stability_repeat_verification_unexpected")
        elif repeat is not None and not repeat.validates_transition(
            previous_result=previous_result,
            current_cycle=cycle,
        ):
            accepted = False
            reasons.append("stability_repeat_verification_binding_failed")

    previous = trial.last_accepted
    stable = False
    stable_streak = 0
    if accepted and previous is not None:
        distance = normalized_goal_distance(previous.goals, cycle.goals)
        stable = max(distance.values(), default=math.inf) <= 1.0
        stable_streak = previous.stable_streak + 1 if stable else 0
    selected_actions: tuple[ShadowAction, ...] = ()
    coarsening_allowed = len(trial.results) >= 2 and all(
        row.accepted_current_state
        and row.p_shadow_maximum <= 0.5
        and row.h_shadow_maximum <= 0.5
        for row in trial.results[-2:]
    )
    if accepted:
        selected_actions, selection_reasons = _select_actions(
            cycle,
            envelope=envelope,
            coarsening_allowed=coarsening_allowed,
        )
        reasons.extend(selection_reasons)
    selected_bindings = tuple(
        (
            row.action_id,
            row.action_sha256,
            _delta_packet_sha256(row.signed_dwr_delta),
            row.transition_action_sha256,
            row.transition_action_file_sha256,
            row.transition_action_identity_sha256,
            row.next_mesh_forest_sha256,
            row.next_degree_map_sha256,
        )
        for row in selected_actions
    )
    selected_ids = tuple(row[0] for row in selected_bindings)

    p_dwr_maximum = (
        cycle.shadows.maximum_normalized_signed_dwr_delta("p")
    )
    p_endpoint_maximum = (
        cycle.shadows.maximum_normalized_endpoint_delta("p")
    )
    h_dwr_maximum = (
        cycle.shadows.maximum_normalized_signed_dwr_delta("h")
    )
    h_endpoint_maximum = (
        cycle.shadows.maximum_normalized_endpoint_delta("h")
    )
    p_maximum = max(p_dwr_maximum, p_endpoint_maximum)
    h_maximum = max(h_dwr_maximum, h_endpoint_maximum)
    p_enrichment_action_count = sum(
        row.kind == "p-up" for row in cycle.shadows.p_actions
    )
    h_enrichment_action_count = sum(
        row.kind == "h-refine" for row in cycle.shadows.h_actions
    )
    p6_saturation = cycle.shadows.p6_saturation
    if p6_saturation.status == "unknown":
        reasons.append("p6_saturation_unmeasured")
    elif p6_saturation.status == "measured_fail":
        reasons.append("p6_saturation_measured_fail")
    elif not p6_saturation.coverage_complete:
        reasons.append("p6_saturation_coverage_incomplete")
    h_level3_saturation = cycle.shadows.h_level3_saturation
    if h_level3_saturation.status == "unknown":
        reasons.append("h_level3_saturation_unmeasured")
    elif h_level3_saturation.status == "measured_fail":
        reasons.append("h_level3_saturation_measured_fail")
    elif not h_level3_saturation.coverage_complete:
        reasons.append("h_level3_saturation_coverage_incomplete")
    h_lane_is_covered = (
        h_enrichment_action_count >= 1
        or (
            h_level3_saturation.level_two_target_count >= 1
            and h_level3_saturation.freeze_passed
        )
    )
    maximum_level_targets_are_covered = (
        h_level3_saturation.level_two_target_count == 0
        or h_level3_saturation.freeze_passed
    )
    freeze_ready = (
        accepted
        and cycle.gates.freeze_passed
        and p_maximum <= 0.5
        and h_maximum <= 0.5
        and stable_streak >= 2
        and not selected_ids
        and p6_saturation.freeze_passed
        and (
            p_enrichment_action_count >= 1
            or p6_saturation.p6_target_count >= 1
        )
        and h_lane_is_covered
        and maximum_level_targets_are_covered
    )
    if not accepted:
        status = "rejected_fail_closed"
    elif freeze_ready:
        status = "freeze_ready"
    elif selected_ids:
        status = "accepted_action_selected"
    else:
        status = "accepted_no_safe_action"
        if "both_shadow_lanes_inside_freeze_threshold" not in reasons:
            reasons.append("no_safe_action_available")

    verification_payload = [
        {
            "action_id": row.action_id,
            "action_sha256": row.action_sha256,
            "transition_action_sha256": row.transition_action_sha256,
            "transition_action_file_sha256": (
                row.transition_action_file_sha256
            ),
            "transition_action_identity_sha256": (
                row.transition_action_identity_sha256
            ),
            "next_mesh_forest_sha256": row.next_mesh_forest_sha256,
            "next_degree_map_sha256": row.next_degree_map_sha256,
            "next_plan_file_sha256": row.next_plan_file_sha256,
            "next_plan_content_sha256": row.next_plan_content_sha256,
            "next_state_sha256": row.next_state_sha256,
            "before_output_sha256": row.before_output_sha256,
            "after_output_sha256": row.after_output_sha256,
            "predicted_deltas": [
                [goal_id, float(value)]
                for goal_id, value in row.predicted_deltas
            ],
            "actual_deltas": [
                [goal_id, float(value)]
                for goal_id, value in row.actual_deltas
            ],
        }
        for row in cycle.executed_action_verifications
    ]
    executed_verification_sha256 = _canonical_sha256(verification_payload)
    repeat_payload = (
        None
        if repeat is None
        else stability_repeat_verification_payload(repeat)
    )
    repeat_sha256 = (
        _canonical_sha256(None)
        if repeat is None
        else repeat.verification_sha256
    )
    certificate_payload: dict[str, Any] = {
        "schema_version": INTERNAL_CERTIFICATE_SCHEMA,
        "cycle_index": cycle.cycle_index,
        "accepted_current_state": accepted,
        "status": status,
        "reasons": list(reasons),
        "selected_action_bindings": [
            list(row) for row in selected_bindings
        ],
        "p_shadow_maximum": p_maximum,
        "h_shadow_maximum": h_maximum,
        "p_enrichment_action_count": p_enrichment_action_count,
        "h_enrichment_action_count": h_enrichment_action_count,
        "stable_from_previous": stable,
        "stable_streak": stable_streak,
        "freeze_ready": freeze_ready,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "goal_sha256": cycle.goals.sha256,
        "mesh_forest_sha256": cycle.mesh_forest_sha256,
        "degree_map_sha256": cycle.degree_map_sha256,
        "plan_file_sha256": cycle.plan_file_sha256,
        "plan_content_sha256": cycle.plan_content_sha256,
        "plan_solver_content_sha256": cycle.plan_solver_content_sha256,
        "state_sha256": cycle.state_sha256,
        "solution_snapshot_sha256": cycle.solution_snapshot_sha256,
        "watchdog_record_file_sha256": (
            cycle.watchdog_record_file_sha256
        ),
        "complete_output_sha256": cycle.complete_output_sha256,
        "full_residual_sha256": cycle.full_residual_sha256,
        "adjoint_bundle_sha256": cycle.adjoint_bundle_sha256,
        "shadow_catalog_sha256": cycle.shadows.sha256,
        "p6_saturation": p6_saturation_authority_payload(
            p6_saturation
        ),
        "h_level3_saturation": h_level3_saturation_authority_payload(
            h_level3_saturation
        ),
        "executed_verification_sha256": executed_verification_sha256,
        "stability_repeat_verification": repeat_payload,
        "stability_repeat_verification_sha256": repeat_sha256,
        "resource_inventory_sha256": cycle.resource_inventory_sha256,
        "gates": _internal_gates_payload(cycle.gates),
    }
    validate_internal_certificate_payload(certificate_payload)
    certificate_sha256 = _canonical_sha256(certificate_payload)
    result = BlindCycleResult(
        cycle_index=cycle.cycle_index,
        accepted_current_state=accepted,
        status=status,
        reasons=tuple(reasons),
        selected_action_ids=selected_ids,
        selected_action_bindings=selected_bindings,
        p_shadow_maximum=p_maximum,
        h_shadow_maximum=h_maximum,
        p_enrichment_action_count=p_enrichment_action_count,
        h_enrichment_action_count=h_enrichment_action_count,
        stable_from_previous=stable,
        stable_streak=stable_streak,
        freeze_ready=freeze_ready,
        goals=cycle.goals,
        mesh_forest_sha256=cycle.mesh_forest_sha256,
        degree_map_sha256=cycle.degree_map_sha256,
        plan_file_sha256=cycle.plan_file_sha256,
        plan_content_sha256=cycle.plan_content_sha256,
        plan_solver_content_sha256=cycle.plan_solver_content_sha256,
        state_sha256=cycle.state_sha256,
        solution_snapshot_sha256=cycle.solution_snapshot_sha256,
        watchdog_record_file_sha256=cycle.watchdog_record_file_sha256,
        complete_output_sha256=cycle.complete_output_sha256,
        full_residual_sha256=cycle.full_residual_sha256,
        adjoint_bundle_sha256=cycle.adjoint_bundle_sha256,
        shadow_catalog_sha256=cycle.shadows.sha256,
        p6_saturation=p6_saturation,
        h_level3_saturation=h_level3_saturation,
        executed_verification_sha256=executed_verification_sha256,
        stability_repeat_verification=repeat,
        stability_repeat_verification_sha256=repeat_sha256,
        internal_certificate=MappingProxyType(certificate_payload),
        internal_certificate_sha256=certificate_sha256,
        resource_inventory_sha256=cycle.resource_inventory_sha256,
        p_shadow_signed_dwr_maximum=p_dwr_maximum,
        p_shadow_endpoint_maximum=p_endpoint_maximum,
        h_shadow_signed_dwr_maximum=h_dwr_maximum,
        h_shadow_endpoint_maximum=h_endpoint_maximum,
    )
    return BlindTrial(
        trial_id=trial.trial_id,
        algorithm_id=trial.algorithm_id,
        source_sha=trial.source_sha,
        initial_path_id=trial.initial_path_id,
        initial_mesh_forest_sha256=trial.initial_mesh_forest_sha256,
        physical_identity_sha256=trial.physical_identity_sha256,
        maximum_cycles=trial.maximum_cycles,
        results=(*trial.results, result),
    )


def compare_frozen_paths(
    left: BlindTrial,
    right: BlindTrial,
) -> Mapping[str, object]:
    """Check that two independently frozen paths agree in blind units."""

    if not left.results or not right.results:
        raise ValueError("both path trials must contain results")
    left_endpoint = left.results[-1]
    right_endpoint = right.results[-1]
    if not left_endpoint.freeze_ready or not right_endpoint.freeze_ready:
        raise ValueError("both path endpoints must be freeze-ready")
    if left.trial_id == right.trial_id:
        raise ValueError("the two frozen trials must have distinct trial IDs")
    if left.initial_path_id == right.initial_path_id:
        raise ValueError("the two frozen trials must use independent paths")
    if left.initial_mesh_forest_sha256 == right.initial_mesh_forest_sha256:
        raise ValueError("the two frozen trials must use distinct initial forests")
    if left.cycle_chain_root_sha256 == right.cycle_chain_root_sha256:
        raise ValueError("the two frozen trials reused one cycle evidence chain")
    for name in ("algorithm_id", "source_sha", "physical_identity_sha256"):
        if getattr(left, name) != getattr(right, name):
            raise ValueError(f"the two frozen trials differ at {name}")
    distances = normalized_goal_distance(
        left_endpoint.goals,
        right_endpoint.goals,
    )
    maximum = max(distances.values(), default=math.inf)
    return MappingProxyType(
        {
            "schema_version": "task035e.two-path-freeze-gate.v1",
            "pass": maximum <= 1.0,
            "algorithm_id": left.algorithm_id,
            "source_sha": left.source_sha,
            "physical_identity_sha256": left.physical_identity_sha256,
            "left_trial_id": left.trial_id,
            "right_trial_id": right.trial_id,
            "left_initial_path_id": left.initial_path_id,
            "right_initial_path_id": right.initial_path_id,
            "left_initial_mesh_forest_sha256": (
                left.initial_mesh_forest_sha256
            ),
            "right_initial_mesh_forest_sha256": (
                right.initial_mesh_forest_sha256
            ),
            "left_cycle_chain_root_sha256": left.cycle_chain_root_sha256,
            "right_cycle_chain_root_sha256": right.cycle_chain_root_sha256,
            "left_output_sha256": left_endpoint.complete_output_sha256,
            "right_output_sha256": right_endpoint.complete_output_sha256,
            "maximum_normalized_goal_distance": maximum,
            "per_goal": dict(distances),
        }
    )


__all__ = [
    "INTERNAL_CERTIFICATE_SCHEMA",
    "STABILITY_REPEAT_VERIFICATION_SCHEMA",
    "BlindCycleInput",
    "BlindCycleResult",
    "BlindTrial",
    "InternalGates",
    "ResourceEnvelope",
    "ShadowVerification",
    "StabilityRepeatVerification",
    "StructuralInventory",
    "advance_blind_trial",
    "compare_frozen_paths",
    "stability_repeat_verification_from_payload",
    "stability_repeat_verification_payload",
    "validate_internal_certificate_payload",
]
