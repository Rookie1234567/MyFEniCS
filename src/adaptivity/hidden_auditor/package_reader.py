"""Candidate preflight and gated access to the sealed reference package."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import (
    CANDIDATE_BUNDLE_SCHEMA,
    CANDIDATE_OUTPUT_SCHEMA,
    FIXED_ORDER_KEYS,
    FIXED_PORTS,
    FORMAL_FIELD_COMPLEX_NAMES,
    FORMAL_FIELD_SCALAR_NAMES,
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    FORMAL_TOTAL_NAMES,
    TWO_PATH_GATE_SCHEMA,
    CandidateFreezeReceipt,
    HiddenAuditContractError,
    canonical_json_sha256,
    exact_mapping,
    finite_float,
    require_sha256,
    require_source_sha,
)


_CANDIDATE_KEYS = frozenset(
    {
        "schema_version",
        "identity",
        "outputs",
        "internal_certificate",
        "resource_authority",
        "two_path_gate",
    }
)
_IDENTITY_KEYS = frozenset(
    {
        "trial_id",
        "algorithm_id",
        "source_sha",
        "initial_path_id",
        "initial_mesh_forest_sha256",
        "cycle_chain_root_sha256",
        "cycle_index",
        "geometry_sha256",
        "material_sha256",
        "incident_sha256",
        "dtn_definition_sha256",
        "postprocessing_sha256",
        "initial_mesh_forest_sha256",
        "cycle_chain_root_sha256",
        "mesh_forest_sha256",
        "degree_map_sha256",
    }
)
_PHYSICAL_IDENTITY_KEYS = (
    "geometry_sha256",
    "material_sha256",
    "incident_sha256",
    "dtn_definition_sha256",
    "postprocessing_sha256",
    "source_sha",
)
_OUTPUT_KEYS = frozenset(
    {
        "schema_version",
        "orders",
        "scalar_observations",
        "complex_observations",
        "full_explicit_true_residual",
    }
)
_ORDER_KEYS = frozenset(
    {
        "port",
        "m",
        "n",
        "propagating",
        "total_power",
        "co_polarized_amplitude",
        "cross_polarized_power",
        "cross_polarized_amplitude",
        "kz",
        "admittance",
        "normalization_identity",
    }
)
_OBSERVATION_KEYS = frozenset({"name", "value"})
_COMPLEX_KEYS = frozenset({"real", "imag"})
_TWO_PATH_KEYS = frozenset(
    {
        "schema_version",
        "pass",
        "algorithm_id",
        "source_sha",
        "physical_identity_sha256",
        "left_trial_id",
        "right_trial_id",
        "left_initial_path_id",
        "right_initial_path_id",
        "left_initial_mesh_forest_sha256",
        "right_initial_mesh_forest_sha256",
        "left_cycle_chain_root_sha256",
        "right_cycle_chain_root_sha256",
        "left_output_sha256",
        "right_output_sha256",
        "maximum_normalized_goal_distance",
        "per_goal",
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
_P6_SATURATION_AUTHORITY_SCHEMA = (
    "task035e.p6-saturation-authority.v1"
)
_P6_SATURATION_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "current_plan_file_sha256",
        "current_mesh_forest_sha256",
        "current_degree_map_sha256",
        "p6_target_count",
        "p6_target_ids",
        "p6_target_ids_sha256",
        "covered_target_count",
        "covered_target_ids",
        "covered_target_ids_sha256",
        "coverage_complete",
        "shadow_only",
        "selectable_as_production",
        "normalized_max",
        "evidence_kind",
        "evidence_sha256",
        "authority_sha256",
    }
)
_H_LEVEL3_SATURATION_AUTHORITY_SCHEMA = (
    "task035e.h-level3-saturation-authority.v1"
)
_H_LEVEL3_SATURATION_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "current_plan_file_sha256",
        "current_mesh_forest_sha256",
        "current_degree_map_sha256",
        "level_two_target_count",
        "level_two_target_ids",
        "level_two_target_ids_sha256",
        "periodic_orbit_count",
        "periodic_orbit_ids",
        "periodic_orbit_ids_sha256",
        "orbit_catalog_sha256",
        "covered_target_count",
        "covered_target_ids",
        "covered_target_ids_sha256",
        "covered_orbit_count",
        "covered_orbit_ids",
        "covered_orbit_ids_sha256",
        "coverage_complete",
        "production_maximum_level",
        "shadow_maximum_level",
        "shadow_only",
        "selectable_as_production",
        "normalized_max",
        "normalized_limit",
        "evidence_kind",
        "evidence_sha256",
        "authority_sha256",
    }
)
_STABILITY_REPEAT_VERIFICATION_SCHEMA = (
    "task035e.stability-repeat-verification.v1"
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
_INTERNAL_GATE_KEYS = frozenset(
    {
        "full_explicit_residual",
        "energy_closure_error",
        "absorption_volume",
        "floquet_residual_pass",
        "hanging_residual_pass",
        "serial_mpi_identity_pass",
        "multilevel_mesh_pass",
        "separated_patch_count",
        "all_local_levels_present",
        "algebraic_budget_fraction",
        "dtn_budget_fraction",
        "postprocess_budget_fraction",
    }
)
_RESOURCE_AUTHORITY_KEYS = frozenset(
    {
        "schema_version",
        "active_dofs",
        "rows",
        "matrix_nnz",
        "factor_nnz",
        "solver_peak_bytes",
        "swap_peak_bytes",
        "mpi_size",
        "same_solver_lifecycle_telemetry",
    }
)

_PREFLIGHT_AUTHORITY = object()


@dataclass(frozen=True, slots=True)
class CandidatePreflight:
    """Opaque proof that every freeze binding passed before hidden access."""

    receipt: CandidateFreezeReceipt
    identity: Mapping[str, Any]
    outputs: Mapping[str, Any]
    internal_certificate: Mapping[str, Any]
    resource_authority: Mapping[str, Any]
    two_path_gate: Mapping[str, Any]
    _authority: object


def _json_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    )


def _validate_complex(value: Any, *, path: str) -> None:
    row = exact_mapping(value, _COMPLEX_KEYS, path=path)
    finite_float(row["real"], path=f"{path}.real")
    finite_float(row["imag"], path=f"{path}.imag")


def _validate_observations(
    value: Any,
    *,
    path: str,
    complex_values: bool,
) -> None:
    if not isinstance(value, list):
        raise HiddenAuditContractError(f"{path} must be an array")
    names: list[str] = []
    for index, observation in enumerate(value):
        item_path = f"{path}[{index}]"
        row = exact_mapping(
            observation,
            _OBSERVATION_KEYS,
            path=item_path,
        )
        if not isinstance(row["name"], str) or not row["name"].strip():
            raise HiddenAuditContractError(
                f"{item_path}.name must be nonempty"
            )
        names.append(row["name"])
        if complex_values:
            _validate_complex(row["value"], path=f"{item_path}.value")
        else:
            finite_float(row["value"], path=f"{item_path}.value")
    if len(names) != len(set(names)):
        raise HiddenAuditContractError(
            f"{path} observation names must be unique"
        )


def _validate_outputs(value: Any) -> Mapping[str, Any]:
    row = exact_mapping(value, _OUTPUT_KEYS, path="candidate.outputs")
    if row["schema_version"] != CANDIDATE_OUTPUT_SCHEMA:
        raise HiddenAuditContractError(
            "candidate.outputs.schema_version is unsupported"
        )
    if not isinstance(row["orders"], list):
        raise HiddenAuditContractError("candidate.outputs.orders must be an array")
    observed_orders: list[tuple[str, int, int]] = []
    for index, order in enumerate(row["orders"]):
        path = f"candidate.outputs.orders[{index}]"
        order_row = exact_mapping(order, _ORDER_KEYS, path=path)
        if (
            order_row["port"] not in FIXED_PORTS
            or isinstance(order_row["m"], bool)
            or not isinstance(order_row["m"], int)
            or isinstance(order_row["n"], bool)
            or not isinstance(order_row["n"], int)
        ):
            raise HiddenAuditContractError(
                f"{path} carries an invalid order identity"
            )
        identity = (
            order_row["port"],
            int(order_row["m"]),
            int(order_row["n"]),
        )
        observed_orders.append(identity)
        if not isinstance(order_row["propagating"], bool):
            raise HiddenAuditContractError(
                f"{path}.propagating must be boolean"
            )
        power = order_row["total_power"]
        cross_power = order_row["cross_polarized_power"]
        if order_row["propagating"]:
            for name, value in (
                ("total_power", power),
                ("cross_polarized_power", cross_power),
            ):
                power_value = finite_float(value, path=f"{path}.{name}")
                if power_value < 0.0:
                    raise HiddenAuditContractError(
                        f"{path}.{name} must be nonnegative"
                    )
        elif power is not None or cross_power is not None:
            raise HiddenAuditContractError(
                f"{path} powers must be null for an evanescent order"
            )
        for name in (
            "co_polarized_amplitude",
            "cross_polarized_amplitude",
            "kz",
            "admittance",
        ):
            _validate_complex(order_row[name], path=f"{path}.{name}")
        if (
            not isinstance(order_row["normalization_identity"], str)
            or not order_row["normalization_identity"].strip()
        ):
            raise HiddenAuditContractError(
                f"{path}.normalization_identity must be nonempty"
            )
    if len(observed_orders) != len(set(observed_orders)):
        raise HiddenAuditContractError(
            "candidate outputs contain duplicate physical diffraction orders"
        )
    port_index = {port: index for index, port in enumerate(FIXED_PORTS)}
    canonical_orders = tuple(
        sorted(
            observed_orders,
            key=lambda identity: (
                port_index[identity[0]],
                -identity[1],
                identity[2],
            ),
        )
    )
    if tuple(observed_orders) != canonical_orders:
        raise HiddenAuditContractError(
            "candidate physical diffraction orders are not canonically sorted"
        )
    missing_fixed = tuple(
        identity for identity in FIXED_ORDER_KEYS if identity not in set(observed_orders)
    )
    if missing_fixed:
        raise HiddenAuditContractError(
            "candidate outputs do not contain the complete fixed N=8 subset"
        )
    _validate_observations(
        row["scalar_observations"],
        path="candidate.outputs.scalar_observations",
        complex_values=False,
    )
    scalar_names = {
        observation["name"] for observation in row["scalar_observations"]
    }
    missing_totals = sorted(set(FORMAL_TOTAL_NAMES) - scalar_names)
    if missing_totals:
        raise HiddenAuditContractError(
            f"candidate outputs are missing formal totals: {missing_totals}"
        )
    missing_field_scalars = sorted(
        set(FORMAL_FIELD_SCALAR_NAMES) - scalar_names
    )
    if missing_field_scalars:
        raise HiddenAuditContractError(
            "candidate outputs are missing formal field scalars: "
            f"{missing_field_scalars}"
        )
    _validate_observations(
        row["complex_observations"],
        path="candidate.outputs.complex_observations",
        complex_values=True,
    )
    complex_names = {
        observation["name"] for observation in row["complex_observations"]
    }
    missing_field_complex = sorted(
        set(FORMAL_FIELD_COMPLEX_NAMES) - complex_names
    )
    if missing_field_complex:
        raise HiddenAuditContractError(
            "candidate outputs are missing formal complex field probes: "
            f"{missing_field_complex}"
        )
    residual = finite_float(
        row["full_explicit_true_residual"],
        path="candidate.outputs.full_explicit_true_residual",
    )
    if residual < 0.0:
        raise HiddenAuditContractError(
            "candidate full explicit residual must be nonnegative"
        )
    return row


def _validate_identity(value: Any) -> Mapping[str, Any]:
    row = exact_mapping(value, _IDENTITY_KEYS, path="candidate.identity")
    for name in ("trial_id", "algorithm_id", "initial_path_id"):
        if not isinstance(row[name], str) or not row[name].strip():
            raise HiddenAuditContractError(
                f"candidate.identity.{name} must be nonempty"
            )
    require_source_sha(
        row["source_sha"],
        path="candidate.identity.source_sha",
    )
    if (
        isinstance(row["cycle_index"], bool)
        or not isinstance(row["cycle_index"], int)
        or not 0 <= row["cycle_index"] <= 5
    ):
        raise HiddenAuditContractError(
            "candidate.identity.cycle_index must be in [0, 5]"
        )
    for name in (
        "geometry_sha256",
        "material_sha256",
        "incident_sha256",
        "dtn_definition_sha256",
        "postprocessing_sha256",
        "mesh_forest_sha256",
        "degree_map_sha256",
    ):
        require_sha256(row[name], path=f"candidate.identity.{name}")
    return row


def _validate_resource_authority(value: Any) -> Mapping[str, Any]:
    row = exact_mapping(
        value,
        _RESOURCE_AUTHORITY_KEYS,
        path="candidate.resource_authority",
    )
    if row["schema_version"] != "task035e.resource-authority.v1":
        raise HiddenAuditContractError(
            "candidate.resource_authority schema is unsupported"
        )
    for name in (
        "active_dofs",
        "rows",
        "matrix_nnz",
        "factor_nnz",
        "solver_peak_bytes",
        "swap_peak_bytes",
    ):
        if (
            isinstance(row[name], bool)
            or not isinstance(row[name], int)
            or row[name] < 0
        ):
            raise HiddenAuditContractError(
                f"candidate.resource_authority.{name} must be nonnegative"
            )
    if row["mpi_size"] != 8:
        raise HiddenAuditContractError(
            "candidate.resource_authority.mpi_size must be eight"
        )
    if row["same_solver_lifecycle_telemetry"] is not True:
        raise HiddenAuditContractError(
            "candidate resource telemetry is not lifecycle-comparable"
        )
    return row


def _validate_stability_repeat_verification(
    value: Any,
    *,
    certificate: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    expected_sha = certificate["stability_repeat_verification_sha256"]
    require_sha256(
        expected_sha,
        path=(
            "candidate.internal_certificate."
            "stability_repeat_verification_sha256"
        ),
    )
    if value is None:
        if expected_sha != canonical_json_sha256(None):
            raise HiddenAuditContractError(
                "empty stability-repeat verification has the wrong digest"
            )
        return None
    row = exact_mapping(
        value,
        _STABILITY_REPEAT_VERIFICATION_KEYS,
        path="candidate.internal_certificate.stability_repeat_verification",
    )
    if (
        row["schema_version"] != _STABILITY_REPEAT_VERIFICATION_SCHEMA
        or row["action_kind"] != "p-keep"
        or not isinstance(row["action_id"], str)
        or not row["action_id"]
    ):
        raise HiddenAuditContractError(
            "candidate stability repeat is not a closed p-keep verification"
        )
    for name in _STABILITY_REPEAT_VERIFICATION_KEYS - {
        "schema_version",
        "action_id",
        "action_kind",
    }:
        require_sha256(
            row[name],
            path=(
                "candidate.internal_certificate."
                f"stability_repeat_verification.{name}"
            ),
        )
    unsigned = dict(row)
    stored_sha = unsigned.pop("verification_sha256")
    if (
        canonical_json_sha256(unsigned) != stored_sha
        or expected_sha != stored_sha
    ):
        raise HiddenAuditContractError(
            "candidate stability-repeat verification self-hash differs"
        )
    invariant_pairs = (
        (
            "previous_mesh_forest_sha256",
            "next_mesh_forest_sha256",
        ),
        ("previous_degree_map_sha256", "next_degree_map_sha256"),
        (
            "previous_plan_solver_content_sha256",
            "next_plan_solver_content_sha256",
        ),
    )
    if any(row[left] != row[right] for left, right in invariant_pairs):
        raise HiddenAuditContractError(
            "candidate p-keep changed mesh, degree, or solver content"
        )
    fresh_pairs = (
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
    )
    if any(row[left] == row[right] for left, right in fresh_pairs):
        raise HiddenAuditContractError(
            "candidate p-keep reused an immutable execution identity"
        )
    current_bindings = {
        "next_state_sha256": certificate["state_sha256"],
        "next_plan_file_sha256": certificate["plan_file_sha256"],
        "next_plan_content_sha256": certificate["plan_content_sha256"],
        "next_plan_solver_content_sha256": certificate[
            "plan_solver_content_sha256"
        ],
        "next_mesh_forest_sha256": certificate["mesh_forest_sha256"],
        "next_degree_map_sha256": certificate["degree_map_sha256"],
        "after_solution_snapshot_sha256": certificate[
            "solution_snapshot_sha256"
        ],
        "after_watchdog_record_file_sha256": certificate[
            "watchdog_record_file_sha256"
        ],
    }
    for name, expected in current_bindings.items():
        if row[name] != expected:
            raise HiddenAuditContractError(
                f"candidate stability repeat differs at {name}"
            )
    return row


def _validate_p6_saturation_authority(
    value: Any,
    *,
    certificate: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Independently replay the closed p6 saturation freeze authority."""

    path = "candidate.internal_certificate.p6_saturation"
    row = exact_mapping(value, _P6_SATURATION_KEYS, path=path)
    if row["schema_version"] != _P6_SATURATION_AUTHORITY_SCHEMA:
        raise HiddenAuditContractError(
            "candidate p6 saturation authority schema is unsupported"
        )
    if row["status"] not in {
        "measured_pass",
        "measured_fail",
        "unknown",
    }:
        raise HiddenAuditContractError(
            "candidate p6 saturation status is unsupported"
        )
    for name in (
        "current_plan_file_sha256",
        "current_mesh_forest_sha256",
        "current_degree_map_sha256",
        "p6_target_ids_sha256",
        "covered_target_ids_sha256",
        "evidence_sha256",
        "authority_sha256",
    ):
        require_sha256(row[name], path=f"{path}.{name}")
    for name in ("p6_target_ids", "covered_target_ids"):
        values = row[name]
        if (
            not isinstance(values, list)
            or any(
                not isinstance(item, str)
                or not item.startswith("cell:r")
                for item in values
            )
            or values != sorted(set(values))
        ):
            raise HiddenAuditContractError(
                f"{path}.{name} is not a canonical cell inventory"
            )
    targets = row["p6_target_ids"]
    covered = row["covered_target_ids"]
    for count_name, values in (
        ("p6_target_count", targets),
        ("covered_target_count", covered),
    ):
        if (
            isinstance(row[count_name], bool)
            or not isinstance(row[count_name], int)
            or row[count_name] != len(values)
        ):
            raise HiddenAuditContractError(
                f"{path}.{count_name} differs from its inventory"
            )
    if row["p6_target_ids_sha256"] != canonical_json_sha256(
        {"canonical_target_ids": targets}
    ):
        raise HiddenAuditContractError(
            "candidate p6 saturation target hash differs"
        )
    if row["covered_target_ids_sha256"] != canonical_json_sha256(
        {"canonical_target_ids": covered}
    ):
        raise HiddenAuditContractError(
            "candidate p6 saturation covered hash differs"
        )
    if not set(covered).issubset(targets):
        raise HiddenAuditContractError(
            "candidate p6 saturation covers non-target leaves"
        )
    coverage_complete = covered == targets
    if (
        not isinstance(row["coverage_complete"], bool)
        or row["coverage_complete"] is not coverage_complete
    ):
        raise HiddenAuditContractError(
            "candidate p6 saturation coverage flag differs"
        )
    if (
        row["shadow_only"] is not True
        or row["selectable_as_production"] is not False
    ):
        raise HiddenAuditContractError(
            "candidate p6 saturation must remain non-production shadow evidence"
        )
    normalized = row["normalized_max"]
    normalized_value = (
        None
        if normalized is None
        else finite_float(normalized, path=f"{path}.normalized_max")
    )
    if normalized_value is not None and normalized_value < 0.0:
        raise HiddenAuditContractError(
            "candidate p6 saturation normalized maximum is negative"
        )
    if targets and row["status"] != "unknown":
        raise HiddenAuditContractError(
            "candidate p6 saturation measured status has no independently "
            "loaded p7 evidence artifact"
        )
    if not targets:
        semantic_pass = (
            row["status"] == "measured_pass"
            and coverage_complete
            and covered == []
            and normalized_value == 0.0
            and row["evidence_kind"] == "zero_p6_targets_vacuous"
        )
    elif row["status"] == "unknown":
        semantic_pass = (
            covered == []
            and not coverage_complete
            and normalized is None
            and row["evidence_kind"] == "no_p7_shadow_evidence"
        )
    else:
        expected_status = (
            "measured_pass"
            if normalized_value is not None and normalized_value <= 0.5
            else "measured_fail"
        )
        semantic_pass = (
            coverage_complete
            and normalized_value is not None
            and row["evidence_kind"] == "independent_p7_shadow"
            and row["status"] == expected_status
        )
    if not semantic_pass:
        raise HiddenAuditContractError(
            "candidate p6 saturation status/content semantics differ"
        )
    if (
        row["current_plan_file_sha256"]
        != certificate["plan_file_sha256"]
        or row["current_mesh_forest_sha256"]
        != certificate["mesh_forest_sha256"]
        or row["current_degree_map_sha256"]
        != certificate["degree_map_sha256"]
    ):
        raise HiddenAuditContractError(
            "candidate p6 saturation plan/forest/degree binding differs"
        )
    unsigned = dict(row)
    authority_sha = unsigned.pop("authority_sha256")
    if canonical_json_sha256(unsigned) != authority_sha:
        raise HiddenAuditContractError(
            "candidate p6 saturation authority self-hash differs"
        )
    return row


def _validate_h_level3_saturation_authority(
    value: Any,
    *,
    certificate: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Independently replay target/orbit-complete level3 h saturation."""

    path = "candidate.internal_certificate.h_level3_saturation"
    row = exact_mapping(value, _H_LEVEL3_SATURATION_KEYS, path=path)
    if row["schema_version"] != _H_LEVEL3_SATURATION_AUTHORITY_SCHEMA:
        raise HiddenAuditContractError(
            "candidate level3 h-saturation authority schema is unsupported"
        )
    if row["status"] not in {
        "measured_pass",
        "measured_fail",
        "unknown",
    }:
        raise HiddenAuditContractError(
            "candidate level3 h-saturation status is unsupported"
        )
    for name in (
        "current_plan_file_sha256",
        "current_mesh_forest_sha256",
        "current_degree_map_sha256",
        "level_two_target_ids_sha256",
        "periodic_orbit_ids_sha256",
        "orbit_catalog_sha256",
        "covered_target_ids_sha256",
        "covered_orbit_ids_sha256",
        "evidence_sha256",
        "authority_sha256",
    ):
        require_sha256(row[name], path=f"{path}.{name}")
    for name in ("level_two_target_ids", "covered_target_ids"):
        values = row[name]
        if (
            not isinstance(values, list)
            or any(
                not isinstance(item, str)
                or not item.startswith("cell:r")
                for item in values
            )
            or values != sorted(set(values))
        ):
            raise HiddenAuditContractError(
                f"{path}.{name} is not a canonical cell inventory"
            )
    for name in ("periodic_orbit_ids", "covered_orbit_ids"):
        values = row[name]
        if (
            not isinstance(values, list)
            or any(
                not isinstance(item, str)
                or not item.startswith("h3-orbit-")
                for item in values
            )
            or values != sorted(set(values))
        ):
            raise HiddenAuditContractError(
                f"{path}.{name} is not a canonical orbit inventory"
            )
    targets = row["level_two_target_ids"]
    orbits = row["periodic_orbit_ids"]
    covered_targets = row["covered_target_ids"]
    covered_orbits = row["covered_orbit_ids"]
    for count_name, values in (
        ("level_two_target_count", targets),
        ("periodic_orbit_count", orbits),
        ("covered_target_count", covered_targets),
        ("covered_orbit_count", covered_orbits),
    ):
        if (
            isinstance(row[count_name], bool)
            or not isinstance(row[count_name], int)
            or row[count_name] != len(values)
        ):
            raise HiddenAuditContractError(
                f"{path}.{count_name} differs from its inventory"
            )
    target_hashes = (
        (
            "level_two_target_ids_sha256",
            {"canonical_target_ids": targets},
        ),
        (
            "covered_target_ids_sha256",
            {"canonical_target_ids": covered_targets},
        ),
        (
            "periodic_orbit_ids_sha256",
            {"canonical_orbit_ids": orbits},
        ),
        (
            "covered_orbit_ids_sha256",
            {"canonical_orbit_ids": covered_orbits},
        ),
    )
    for name, payload in target_hashes:
        if row[name] != canonical_json_sha256(payload):
            raise HiddenAuditContractError(
                f"candidate level3 h-saturation {name} differs"
            )
    if not set(covered_targets).issubset(targets):
        raise HiddenAuditContractError(
            "candidate level3 h-saturation covers non-target leaves"
        )
    if not set(covered_orbits).issubset(orbits):
        raise HiddenAuditContractError(
            "candidate level3 h-saturation covers unknown orbits"
        )
    coverage_complete = (
        covered_targets == targets and covered_orbits == orbits
    )
    if (
        not isinstance(row["coverage_complete"], bool)
        or row["coverage_complete"] is not coverage_complete
    ):
        raise HiddenAuditContractError(
            "candidate level3 h-saturation coverage flag differs"
        )
    if (
        row["production_maximum_level"] != 2
        or row["shadow_maximum_level"] != 3
        or row["shadow_only"] is not True
        or row["selectable_as_production"] is not False
    ):
        raise HiddenAuditContractError(
            "candidate level3 h-saturation changed the production level cap"
        )
    normalized_limit = finite_float(
        row["normalized_limit"],
        path=f"{path}.normalized_limit",
    )
    if normalized_limit != 0.5:
        raise HiddenAuditContractError(
            "candidate level3 h-saturation normalized limit differs"
        )
    normalized = row["normalized_max"]
    normalized_value = (
        None
        if normalized is None
        else finite_float(normalized, path=f"{path}.normalized_max")
    )
    if normalized_value is not None and normalized_value < 0.0:
        raise HiddenAuditContractError(
            "candidate level3 h-saturation normalized maximum is negative"
        )
    if targets and row["status"] != "unknown":
        raise HiddenAuditContractError(
            "candidate level3 h-saturation measured status has no "
            "independently loaded level3 evidence artifact"
        )
    if not targets:
        semantic_pass = (
            orbits == []
            and covered_targets == []
            and covered_orbits == []
            and row["status"] == "measured_pass"
            and coverage_complete
            and normalized_value == 0.0
            and row["evidence_kind"]
            == "zero_level2_targets_vacuous"
        )
    elif row["status"] == "unknown":
        semantic_pass = (
            bool(orbits)
            and covered_targets == []
            and covered_orbits == []
            and not coverage_complete
            and normalized is None
            and row["evidence_kind"]
            == "no_independent_global_level3_evidence"
        )
    else:
        expected_status = (
            "measured_pass"
            if normalized_value is not None
            and normalized_value <= normalized_limit
            else "measured_fail"
        )
        semantic_pass = (
            bool(orbits)
            and coverage_complete
            and normalized_value is not None
            and row["evidence_kind"]
            == "independent_global_level3_shadow"
            and row["status"] == expected_status
        )
    if not semantic_pass:
        raise HiddenAuditContractError(
            "candidate level3 h-saturation status/content semantics differ"
        )
    if (
        row["current_plan_file_sha256"]
        != certificate["plan_file_sha256"]
        or row["current_mesh_forest_sha256"]
        != certificate["mesh_forest_sha256"]
        or row["current_degree_map_sha256"]
        != certificate["degree_map_sha256"]
    ):
        raise HiddenAuditContractError(
            "candidate level3 h-saturation plan/forest/degree binding differs"
        )
    unsigned = dict(row)
    authority_sha = unsigned.pop("authority_sha256")
    if canonical_json_sha256(unsigned) != authority_sha:
        raise HiddenAuditContractError(
            "candidate level3 h-saturation authority self-hash differs"
        )
    return row


def _validate_internal_certificate(
    value: Any,
    *,
    receipt: CandidateFreezeReceipt,
    outputs: Mapping[str, Any],
    resource_authority: Mapping[str, Any],
) -> Mapping[str, Any]:
    row = exact_mapping(
        value,
        _INTERNAL_CERTIFICATE_KEYS,
        path="candidate.internal_certificate",
    )
    if (
        row["schema_version"]
        != "task035e.blind-internal-certificate.v2"
    ):
        raise HiddenAuditContractError(
            "candidate internal certificate schema is unsupported"
        )
    for name in (
        "accepted_current_state",
        "stable_from_previous",
        "freeze_ready",
    ):
        if not isinstance(row[name], bool):
            raise HiddenAuditContractError(
                f"candidate.internal_certificate.{name} must be boolean"
            )
    if row["accepted_current_state"] is not True:
        raise HiddenAuditContractError("blind current state was not accepted")
    if row["status"] != "freeze_ready" or row["freeze_ready"] is not True:
        raise HiddenAuditContractError(
            "internal certificate is not independently freeze-ready"
        )
    if (
        isinstance(row["cycle_index"], bool)
        or not isinstance(row["cycle_index"], int)
        or row["cycle_index"] != receipt.cycle_index
    ):
        raise HiddenAuditContractError(
            "internal certificate cycle does not match the receipt"
        )
    if not isinstance(row["reasons"], list) or any(
        not isinstance(item, str) for item in row["reasons"]
    ):
        raise HiddenAuditContractError(
            "internal certificate reasons must be strings"
        )
    if row["selected_action_bindings"] != []:
        raise HiddenAuditContractError(
            "freeze-ready certificate still selects an action"
        )
    for name in ("p_shadow_maximum", "h_shadow_maximum"):
        value_number = finite_float(
            row[name],
            path=f"candidate.internal_certificate.{name}",
        )
        if not 0.0 <= value_number <= 0.5:
            raise HiddenAuditContractError(
                f"candidate.internal_certificate.{name} exceeds F1"
            )
    p6_saturation = _validate_p6_saturation_authority(
        row["p6_saturation"],
        certificate=row,
    )
    h_level3_saturation = _validate_h_level3_saturation_authority(
        row["h_level3_saturation"],
        certificate=row,
    )
    for name in ("p_enrichment_action_count", "h_enrichment_action_count"):
        if (
            isinstance(row[name], bool)
            or not isinstance(row[name], int)
            or row[name] < 0
        ):
            raise HiddenAuditContractError(
                f"candidate.internal_certificate.{name} is invalid"
            )
    if (
        row["h_enrichment_action_count"] < 1
        and h_level3_saturation["level_two_target_count"] < 1
    ):
        raise HiddenAuditContractError(
            "candidate internal certificate lacks a real h lane or "
            "level3 saturation coverage"
        )
    if (
        row["p_enrichment_action_count"] < 1
        and p6_saturation["p6_target_count"] < 1
    ):
        raise HiddenAuditContractError(
            "candidate internal certificate lacks a real p lane"
        )
    if (
        p6_saturation["status"] != "measured_pass"
        or p6_saturation["coverage_complete"] is not True
    ):
        raise HiddenAuditContractError(
            "candidate p6 saturation is not independently freeze-ready"
        )
    if (
        h_level3_saturation["level_two_target_count"] >= 1
        and (
            h_level3_saturation["status"] != "measured_pass"
            or h_level3_saturation["coverage_complete"] is not True
        )
    ):
        raise HiddenAuditContractError(
            "candidate level3 h saturation is not independently freeze-ready"
        )
    if (
        isinstance(row["stable_streak"], bool)
        or not isinstance(row["stable_streak"], int)
        or row["stable_streak"] < 2
    ):
        raise HiddenAuditContractError(
            "internal certificate lacks two stable accepted transitions"
        )
    if (
        isinstance(row["formal_goal_count"], bool)
        or not isinstance(row["formal_goal_count"], int)
        or row["formal_goal_count"] != len(FORMAL_GOAL_IDS)
    ):
        raise HiddenAuditContractError(
            "internal certificate formal goal count is incomplete"
        )
    if (
        row["formal_goal_inventory_sha256"]
        != FORMAL_GOAL_INVENTORY_SHA256
    ):
        raise HiddenAuditContractError(
            "internal certificate formal goal inventory differs"
        )
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
        require_sha256(
            row[name],
            path=f"candidate.internal_certificate.{name}",
        )
    _validate_stability_repeat_verification(
        row["stability_repeat_verification"],
        certificate=row,
    )
    bindings = {
        "mesh_forest_sha256": receipt.mesh_forest_sha256,
        "degree_map_sha256": receipt.degree_map_sha256,
        "complete_output_sha256": receipt.output_sha256,
        "resource_inventory_sha256": receipt.resource_inventory_sha256,
    }
    for name, expected in bindings.items():
        if row[name] != expected:
            raise HiddenAuditContractError(
                f"internal certificate differs from the receipt at {name}"
            )
    if canonical_json_sha256(outputs) != row["complete_output_sha256"]:
        raise HiddenAuditContractError(
            "internal certificate does not bind candidate outputs"
        )
    if (
        canonical_json_sha256(resource_authority)
        != row["resource_inventory_sha256"]
    ):
        raise HiddenAuditContractError(
            "internal certificate does not bind resource authority"
        )
    gates = exact_mapping(
        row["gates"],
        _INTERNAL_GATE_KEYS,
        path="candidate.internal_certificate.gates",
    )
    for name in (
        "full_explicit_residual",
        "energy_closure_error",
        "absorption_volume",
        "algebraic_budget_fraction",
        "dtn_budget_fraction",
        "postprocess_budget_fraction",
    ):
        number = finite_float(
            gates[name],
            path=f"candidate.internal_certificate.gates.{name}",
        )
        if number < 0.0:
            raise HiddenAuditContractError(
                f"candidate internal gate {name} must be nonnegative"
            )
    if gates["full_explicit_residual"] > 1.0e-9:
        raise HiddenAuditContractError("internal residual gate failed")
    if gates["energy_closure_error"] > 1.0e-9:
        raise HiddenAuditContractError("internal energy gate failed")
    for name in (
        "floquet_residual_pass",
        "hanging_residual_pass",
        "serial_mpi_identity_pass",
        "multilevel_mesh_pass",
        "all_local_levels_present",
    ):
        if gates[name] is not True:
            raise HiddenAuditContractError(
                f"candidate internal gate {name} did not pass"
            )
    if (
        isinstance(gates["separated_patch_count"], bool)
        or not isinstance(gates["separated_patch_count"], int)
        or gates["separated_patch_count"] < 2
    ):
        raise HiddenAuditContractError(
            "candidate internal gate lacks separated patches"
        )
    for name in (
        "algebraic_budget_fraction",
        "dtn_budget_fraction",
        "postprocess_budget_fraction",
    ):
        if float(gates[name]) > 0.10:
            raise HiddenAuditContractError(
                f"candidate internal gate {name} exceeds F4"
            )
    return row


def _validate_two_path_gate(
    value: Any,
    *,
    receipt: CandidateFreezeReceipt,
) -> Mapping[str, Any]:
    row = exact_mapping(value, _TWO_PATH_KEYS, path="candidate.two_path_gate")
    if row["schema_version"] != TWO_PATH_GATE_SCHEMA:
        raise HiddenAuditContractError(
            "candidate.two_path_gate.schema_version is unsupported"
        )
    if row["pass"] is not True:
        raise HiddenAuditContractError(
            "candidate two-path agreement did not pass"
        )
    if row["algorithm_id"] != receipt.algorithm_id:
        raise HiddenAuditContractError(
            "two-path gate algorithm differs from the frozen candidate"
        )
    if row["source_sha"] != receipt.source_sha:
        raise HiddenAuditContractError(
            "two-path gate source differs from the frozen candidate"
        )
    if row["physical_identity_sha256"] != receipt.physical_identity_sha256:
        raise HiddenAuditContractError(
            "two-path gate physical identity differs from the candidate"
        )
    left_trial = row["left_trial_id"]
    right_trial = row["right_trial_id"]
    if (
        not isinstance(left_trial, str)
        or not left_trial
        or not isinstance(right_trial, str)
        or not right_trial
        or left_trial == right_trial
    ):
        raise HiddenAuditContractError(
            "two-path gate requires two distinct trial IDs"
        )
    if receipt.trial_id not in {left_trial, right_trial}:
        raise HiddenAuditContractError(
            "frozen candidate is not one of the two audited trials"
        )
    left_path = row["left_initial_path_id"]
    right_path = row["right_initial_path_id"]
    if (
        not isinstance(left_path, str)
        or not left_path
        or not isinstance(right_path, str)
        or not right_path
        or left_path == right_path
    ):
        raise HiddenAuditContractError(
            "two-path gate requires two distinct initial paths"
        )
    if receipt.initial_path_id not in {left_path, right_path}:
        raise HiddenAuditContractError(
            "frozen candidate is not one of the two audited paths"
        )
    left_forest = require_sha256(
        row["left_initial_mesh_forest_sha256"],
        path="candidate.two_path_gate.left_initial_mesh_forest_sha256",
    )
    right_forest = require_sha256(
        row["right_initial_mesh_forest_sha256"],
        path="candidate.two_path_gate.right_initial_mesh_forest_sha256",
    )
    if left_forest == right_forest:
        raise HiddenAuditContractError(
            "two-path gate reused one initial mesh forest"
        )
    left_chain = require_sha256(
        row["left_cycle_chain_root_sha256"],
        path="candidate.two_path_gate.left_cycle_chain_root_sha256",
    )
    right_chain = require_sha256(
        row["right_cycle_chain_root_sha256"],
        path="candidate.two_path_gate.right_cycle_chain_root_sha256",
    )
    if left_chain == right_chain:
        raise HiddenAuditContractError(
            "two-path gate reused one cycle evidence chain"
        )
    if receipt.trial_id == left_trial:
        expected_path = left_path
        expected_forest = left_forest
        expected_chain = left_chain
    else:
        expected_path = right_path
        expected_forest = right_forest
        expected_chain = right_chain
    if (
        receipt.initial_path_id != expected_path
        or receipt.initial_mesh_forest_sha256 != expected_forest
        or receipt.cycle_chain_root_sha256 != expected_chain
    ):
        raise HiddenAuditContractError(
            "two-path gate endpoint lineage differs from the freeze receipt"
        )
    left_output = require_sha256(
        row["left_output_sha256"],
        path="candidate.two_path_gate.left_output_sha256",
    )
    right_output = require_sha256(
        row["right_output_sha256"],
        path="candidate.two_path_gate.right_output_sha256",
    )
    expected_output = left_output if receipt.trial_id == left_trial else right_output
    if expected_output != receipt.output_sha256:
        raise HiddenAuditContractError(
            "two-path gate does not bind the frozen candidate output"
        )
    maximum = finite_float(
        row["maximum_normalized_goal_distance"],
        path="candidate.two_path_gate.maximum_normalized_goal_distance",
    )
    if maximum < 0.0 or maximum > 1.0:
        raise HiddenAuditContractError(
            "two-path maximum normalized distance exceeds one"
        )
    if not isinstance(row["per_goal"], Mapping):
        raise HiddenAuditContractError(
            "candidate.two_path_gate.per_goal must be an object"
        )
    if set(row["per_goal"]) != set(FORMAL_GOAL_IDS):
        raise HiddenAuditContractError(
            "two-path gate must contain the complete formal goal inventory"
        )
    distances = tuple(
        finite_float(
            row["per_goal"][goal_id],
            path=f"candidate.two_path_gate.per_goal.{goal_id}",
        )
        for goal_id in FORMAL_GOAL_IDS
    )
    if any(distance < 0.0 or distance > 1.0 for distance in distances):
        raise HiddenAuditContractError(
            "two-path per-goal distance exceeds one"
        )
    if not math.isclose(
        maximum,
        max(distances, default=0.0),
        rel_tol=0.0,
        abs_tol=1.0e-15,
    ):
        raise HiddenAuditContractError(
            "two-path maximum does not match the per-goal distances"
        )
    return row


def preflight_frozen_candidate(
    freeze_receipt: Mapping[str, Any],
    candidate_bundle: Mapping[str, Any],
) -> CandidatePreflight:
    """Verify every frozen binding without opening any hidden reference."""

    receipt = CandidateFreezeReceipt.from_mapping(freeze_receipt)
    candidate = exact_mapping(
        candidate_bundle,
        _CANDIDATE_KEYS,
        path="candidate",
    )
    if candidate["schema_version"] != CANDIDATE_BUNDLE_SCHEMA:
        raise HiddenAuditContractError(
            "candidate.schema_version is unsupported"
        )
    identity = _validate_identity(candidate["identity"])
    outputs = _validate_outputs(candidate["outputs"])
    resource_authority = _validate_resource_authority(
        candidate["resource_authority"]
    )
    internal_certificate = _validate_internal_certificate(
        candidate["internal_certificate"],
        receipt=receipt,
        outputs=outputs,
        resource_authority=resource_authority,
    )
    if not isinstance(candidate["two_path_gate"], Mapping):
        raise HiddenAuditContractError(
            "candidate.two_path_gate must be an object"
        )

    identity_fields = (
        "trial_id",
        "algorithm_id",
        "source_sha",
        "initial_path_id",
        "initial_mesh_forest_sha256",
        "cycle_chain_root_sha256",
        "cycle_index",
        "mesh_forest_sha256",
        "degree_map_sha256",
    )
    for name in identity_fields:
        if identity[name] != getattr(receipt, name):
            raise HiddenAuditContractError(
                f"freeze receipt and candidate {name} differ"
            )
    physical_identity = {
        name: identity[name] for name in _PHYSICAL_IDENTITY_KEYS
    }
    bindings = (
        (
            "physical identity",
            canonical_json_sha256(physical_identity),
            receipt.physical_identity_sha256,
        ),
        (
            "output",
            canonical_json_sha256(outputs),
            receipt.output_sha256,
        ),
        (
            "internal certificate",
            canonical_json_sha256(candidate["internal_certificate"]),
            receipt.internal_certificate_sha256,
        ),
        (
            "resource authority",
            canonical_json_sha256(candidate["resource_authority"]),
            receipt.resource_inventory_sha256,
        ),
        (
            "two-path gate",
            canonical_json_sha256(candidate["two_path_gate"]),
            receipt.two_path_gate_sha256,
        ),
    )
    for label, actual, expected in bindings:
        if actual != expected:
            raise HiddenAuditContractError(
                f"frozen {label} SHA-256 mismatch"
            )
    two_path_gate = _validate_two_path_gate(
        candidate["two_path_gate"],
        receipt=receipt,
    )
    return CandidatePreflight(
        receipt=receipt,
        identity=MappingProxyType(_json_copy(identity)),
        outputs=MappingProxyType(_json_copy(outputs)),
        internal_certificate=MappingProxyType(
            _json_copy(internal_certificate)
        ),
        resource_authority=MappingProxyType(
            _json_copy(resource_authority)
        ),
        two_path_gate=MappingProxyType(_json_copy(two_path_gate)),
        _authority=_PREFLIGHT_AUTHORITY,
    )


def _load_sealed_reference_package(path: Any) -> dict[str, Any]:
    from ..reference_certifier import read_sealed_reference_package

    return read_sealed_reference_package(path)


def read_qualified_reference_after_preflight(
    preflight: CandidatePreflight,
    path: Any,
) -> dict[str, Any]:
    """Open hidden data only for a genuine, fully verified preflight token."""

    if (
        not isinstance(preflight, CandidatePreflight)
        or preflight._authority is not _PREFLIGHT_AUTHORITY
    ):
        raise HiddenAuditContractError(
            "sealed reference access requires a valid candidate preflight"
        )
    package = _load_sealed_reference_package(path)
    certification = package["certification"]
    if (
        certification["qualified"] is not True
        or certification["status"] != "qualified"
        or certification["gates"]["passed"] is not True
        or not all(
            value is True
            for key, value in certification["gates"].items()
            if key != "passed"
        )
    ):
        raise HiddenAuditContractError(
            "sealed reference package is not fully qualified"
        )
    h5_identity = package["runs"][2]["identity"]
    for name in _PHYSICAL_IDENTITY_KEYS:
        if h5_identity[name] != preflight.identity[name]:
            raise HiddenAuditContractError(
                f"candidate/reference physical identity differs at {name}"
            )
    return package


__all__ = [
    "CandidatePreflight",
    "preflight_frozen_candidate",
    "read_qualified_reference_after_preflight",
]
