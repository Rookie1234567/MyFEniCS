"""Fail-closed aggregation for Task033 Hybrid modal-truncation funnels.

The expensive Hybrid shards are executed by ``run_task033_memory_watchdog``.
This module consumes only its lightweight promoted summaries.  A single M
value is never a convergence result: qualification requires the ordered
M80/M120/M160 funnel, and M240 is considered only when M120 -> M160 fails.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any


FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MANDATORY_TOTAL_TOLERANCE = 1.0e-5
STRONG_TOTAL_TOLERANCE = 1.0e-6
MANDATORY_ORDER_RELATIVE_TOLERANCE = 1.0e-3
STRONG_ORDER_RELATIVE_TOLERANCE = 1.0e-4
SIGNIFICANT_ORDER_POWER = 1.0e-8
WEAK_ORDER_ABSOLUTE_TOLERANCE = 1.0e-8
CONTROLLED_PHYSICAL_GATE_FAILURES = frozenset(
    {
        "sampled_interface_h_t_relative_l2_le_1e-2",
        "volume_absorption_full3d_abs_delta_le_1e-5",
        "middle_plane_e_relative_l2_le_5e-3",
        "middle_plane_h_relative_l2_le_5e-3",
    }
)
P1_H5_CAPACITY_FAILURE = (
    "M160 is not qualified because p1/h5 supplies only 120 finite admissible "
    "modes per direction before singular-K2 numerical-infinity roots"
)
P1_TERMINAL_PHYSICAL_FAILURE = (
    "M160 is not qualified because final p1 physical field gates failed "
    "against the bound full3d reference"
)
P1_TERMINAL_REFERENCE_RECORD = (
    "benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/"
    "full3d_h3_reference.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _complex(value: Any) -> complex | None:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if len(value) != 2:
            return None
        real = _finite(value[0])
        imag = _finite(value[1])
        if real is None or imag is None:
            return None
        return complex(real, imag)
    try:
        result = complex(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result.real) and math.isfinite(result.imag) else None


def _source(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    source = payload.get("source")
    return source if isinstance(source, Mapping) else {}


def _measurements(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    value = payload.get("measurements")
    return value if isinstance(value, Mapping) else {}


def _source_sha(payload: Mapping[str, Any]) -> str | None:
    source = _source(payload)
    value = (
        source.get("head_before_sha")
        or source.get("commit_sha")
        or source.get("source_commit_full_sha")
    )
    if not isinstance(value, str):
        return None
    value = value.lower()
    return value if FULL_SHA_RE.fullmatch(value) is not None else None


def _source_clean(payload: Mapping[str, Any]) -> bool:
    source = _source(payload)
    sha = _source_sha(payload)
    verified = source.get("verified_clean_sha")
    verified_matches = (
        verified is None
        or (isinstance(verified, str) and verified.lower() == sha)
    )
    legacy_clean = source.get("tracked_source_dirty") is False
    stable_scan_clean = bool(
        source.get("tracked_status_before") == ""
        and source.get("tracked_status_after") == ""
        and source.get("source_stable_during_run") is True
    )
    return bool(
        sha is not None
        and verified_matches
        and (legacy_clean or stable_scan_clean)
        and source.get("source_clean_verified", True) is True
    )


def _case(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    value = _measurements(payload).get("case")
    return value if isinstance(value, Mapping) else {}


def _validation(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    measurements = _measurements(payload)
    value = measurements.get("validation")
    return value if isinstance(value, Mapping) else measurements


def _port_power(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    value = _measurements(payload).get("port_power")
    if not isinstance(value, Mapping):
        value = _validation(payload).get("port_power")
    return value if isinstance(value, Mapping) else {}


def _orders(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = _measurements(payload).get("external_diffraction_orders")
    if not isinstance(value, list):
        value = _validation(payload).get("external_diffraction_orders")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _order_key(row: Mapping[str, Any]) -> tuple[str, int, int, str] | None:
    try:
        return (
            str(row["side"]),
            int(row["m"]),
            int(row["n"]),
            str(row["polarization"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _individual_physical_gates(payload: Mapping[str, Any]) -> dict[str, Any]:
    measurements = _measurements(payload)
    qualification = measurements.get("qualification")
    if not isinstance(qualification, Mapping):
        qualification = {}
    gates = measurements.get("gates")
    if not isinstance(gates, Mapping):
        gates = {}
    solve = measurements.get("solve")
    if not isinstance(solve, Mapping):
        solve = {}
    residual = _finite(solve.get("true_relative_residual"))
    gate_values_are_boolean = all(type(value) is bool for value in gates.values())
    all_reported_gates_pass = bool(gates) and gate_values_are_boolean and all(gates.values())
    return {
        "integration_pass": qualification.get("integration_pass") is True,
        "algebraic_chain_pass": qualification.get("algebraic_chain_pass") is True,
        "physical_field_gates_pass": qualification.get("physical_field_gates_pass") is True,
        "task033_physical_truncation_allowed": (
            qualification.get("task033_physical_truncation_allowed") is True
        ),
        "candidate_pool_is_twice_requested_modes": (
            _candidate_pool_is_exactly_twice_retained(payload)
        ),
        "true_relative_residual": residual,
        "true_relative_residual_le_1e-9": residual is not None and residual <= 1.0e-9,
        "all_reported_gates_pass": all_reported_gates_pass,
    }


def _candidate_pool_is_exactly_twice_retained(
    payload: Mapping[str, Any],
) -> bool:
    retained = _case(payload).get("requested_modes_per_direction")
    return bool(
        type(retained) is int
        and retained > 0
        and payload.get("requested_modes") == retained
        and payload.get("candidate_modes") == 2 * retained
    )


def _external_watchdog_pass(payload: Mapping[str, Any]) -> bool:
    status = payload.get("status")
    resource = payload.get("resource_authority")
    resource = resource if isinstance(resource, Mapping) else {}
    resource_gate = resource.get("gate")
    resource_gate = resource_gate if isinstance(resource_gate, Mapping) else {}
    source_gate = payload.get("source_gate")
    source_gate = source_gate if isinstance(source_gate, Mapping) else {}
    launch_gate = payload.get("launch_gate")
    launch_gate = launch_gate if isinstance(launch_gate, Mapping) else {}
    nested_gates_pass = bool(
        resource_gate.get("pass") is True
        and source_gate.get("pass") is True
        and launch_gate.get("pass") is True
    )
    # ``measured_shard_pass`` is the Task033 identity after the watchdog
    # hardening.  The former ``formal_measured_pass`` is intentionally rejected.
    measured_pass = bool(
        status == "measured_shard_pass"
        and payload.get("target") == "hybrid"
        and payload.get("return_code") == 0
        and payload.get("no_swap") is True
        and payload.get("terminated_for_memory") is False
        and payload.get("terminated_for_timeout") is False
        and payload.get("terminated_for_authority_unreadable", False) is False
        and payload.get("memory_authority_pass") is True
        and nested_gates_pass
        and _candidate_pool_is_exactly_twice_retained(payload)
        and _command_mpi_size(payload.get("command")) == 4
    )
    if measured_pass:
        return True
    return bool(
        _controlled_physical_truncation_negative(payload)
        or _controlled_modal_basis_capacity_negative(payload)
    )


def _command_mpi_size(command: Any) -> int | None:
    if not isinstance(command, Sequence) or isinstance(command, (str, bytes)):
        return None
    values = [str(value) for value in command]
    try:
        return int(values[values.index("-n") + 1])
    except (ValueError, IndexError):
        return None


def _controlled_physical_truncation_negative(
    payload: Mapping[str, Any],
) -> bool:
    """Accept only a complete fail-closed physical-truncation negative.

    This is an external-execution contract, not an individual physical pass.
    It lets M80/M120 contribute measured fields to the funnel while preserving
    the existing physical qualification requirement on M160/the selected end.
    """

    measurements = _measurements(payload)
    qualification = measurements.get("qualification")
    qualification = qualification if isinstance(qualification, Mapping) else {}
    gates = measurements.get("gates")
    gates = gates if isinstance(gates, Mapping) else {}
    solve = measurements.get("solve")
    solve = solve if isinstance(solve, Mapping) else {}
    residual = _finite(solve.get("true_relative_residual"))
    resource = payload.get("resource_authority")
    resource = resource if isinstance(resource, Mapping) else {}
    resource_gate = resource.get("gate")
    resource_gate = resource_gate if isinstance(resource_gate, Mapping) else {}
    source_gate = payload.get("source_gate")
    source_gate = source_gate if isinstance(source_gate, Mapping) else {}
    launch_gate = payload.get("launch_gate")
    launch_gate = launch_gate if isinstance(launch_gate, Mapping) else {}
    gates_are_boolean = bool(gates) and all(type(value) is bool for value in gates.values())
    failed_gate_names = [name for name, value in gates.items() if value is False]
    only_physical_gates_failed = bool(
        gates_are_boolean
        and failed_gate_names
        and set(failed_gate_names).issubset(CONTROLLED_PHYSICAL_GATE_FAILURES)
    )
    return bool(
        payload.get("status") == "formal_not_pass"
        and payload.get("target") == "hybrid"
        and type(payload.get("return_code")) is int
        and payload.get("return_code") == 2
        and payload.get("formal_pass") is False
        and payload.get("numeric_pass") is False
        and payload.get("no_swap") is True
        and payload.get("terminated_for_memory") is False
        and payload.get("terminated_for_timeout") is False
        and payload.get("terminated_for_authority_unreadable") is False
        and payload.get("memory_authority_pass") is True
        and resource_gate.get("pass") is True
        and source_gate.get("pass") is True
        and launch_gate.get("pass") is True
        and _candidate_pool_is_exactly_twice_retained(payload)
        and _command_mpi_size(payload.get("command")) == 4
        and measurements.get("status") == "physical_integration_failed"
        and qualification.get("integration_pass") is False
        and qualification.get("algebraic_chain_pass") is True
        and qualification.get("physical_field_gates_pass") is False
        and qualification.get("task033_physical_truncation_allowed") is True
        and qualification.get("mode_count_converged") is False
        and qualification.get("official_record") is False
        and residual is not None
        and residual <= 1.0e-9
        and only_physical_gates_failed
    )


def _controlled_modal_basis_capacity_negative(
    payload: Mapping[str, Any],
) -> bool:
    """Recognize only the measured p1/h5 M160 singular-K2 capacity boundary."""

    measurements = _measurements(payload)
    case = _case(payload)
    qualification = measurements.get("qualification")
    qualification = qualification if isinstance(qualification, Mapping) else {}
    capacity = measurements.get("modal_basis_capacity")
    capacity = capacity if isinstance(capacity, Mapping) else {}
    gates = measurements.get("gates")
    gates = gates if isinstance(gates, Mapping) else {}
    solve = measurements.get("solve")
    solve = solve if isinstance(solve, Mapping) else {}
    hybrid = measurements.get("hybrid_system")
    hybrid = hybrid if isinstance(hybrid, Mapping) else {}
    resource = payload.get("resource_authority")
    resource = resource if isinstance(resource, Mapping) else {}
    resource_gate = resource.get("gate")
    resource_gate = resource_gate if isinstance(resource_gate, Mapping) else {}
    source_gate = payload.get("source_gate")
    source_gate = source_gate if isinstance(source_gate, Mapping) else {}
    launch_gate = payload.get("launch_gate")
    launch_gate = launch_gate if isinstance(launch_gate, Mapping) else {}
    return bool(
        payload.get("status") == "formal_not_pass"
        and payload.get("target") == "hybrid"
        and payload.get("return_code") == 2
        and payload.get("formal_pass") is False
        and payload.get("numeric_pass") is False
        and payload.get("no_swap") is True
        and payload.get("terminated_for_memory") is False
        and payload.get("terminated_for_timeout") is False
        and payload.get("terminated_for_authority_unreadable") is False
        and payload.get("memory_authority_pass") is True
        and resource_gate.get("pass") is True
        and source_gate.get("pass") is True
        and launch_gate.get("pass") is True
        and _command_mpi_size(payload.get("command")) == 4
        and _candidate_pool_is_exactly_twice_retained(payload)
        and case.get("degree") == 1
        and _finite(case.get("h_nm")) == 5.0
        and case.get("requested_modes_per_direction") == 160
        and case.get("candidate_modes_per_target_branch") == 320
        and measurements.get("status")
        == "insufficient_finite_admissible_modes"
        and hybrid.get("primary_solver_path")
        == "modal-schur-memory-minimal"
        and "true_relative_residual" in solve
        and solve.get("true_relative_residual") is None
        and gates == {"finite_admissible_mode_capacity": False}
        and qualification.get("capacity_disposition")
        == "insufficient_finite_admissible_modes"
        and qualification.get("modal_basis_capacity_pass") is False
        and qualification.get("integration_pass") is False
        and qualification.get("algebraic_chain_pass") is False
        and qualification.get("physical_field_gates_pass") is False
        and qualification.get("task033_physical_truncation_allowed") is False
        and qualification.get("mode_count_converged") is False
        and qualification.get("official_record") is False
        and is_exact_p1_h5_modal_basis_capacity(capacity)
    )


def _controlled_p1_terminal_physical_negative(
    payload: Mapping[str, Any],
) -> bool:
    """Recognize the terminal M160 physical negative for safe non-h5 p1 rows."""

    case = _case(payload)
    return bool(
        _controlled_physical_truncation_negative(payload)
        and case.get("degree") == 1
        and _finite(case.get("h_nm")) in {3.0, 2.5, 2.0, 1.5}
        and case.get("requested_modes_per_direction") == 160
        and case.get("candidate_modes_per_target_branch") == 320
        and case.get("bottom_interface_nm") == 10.0
        and case.get("top_interface_nm") == 110.0
        and case.get("graded_reference_h_nm") is None
        and _terminal_reference_evidence(payload) is not None
    )


def is_exact_p1_terminal_reference_evidence(value: Any) -> bool:
    """Validate the compact binding to the frozen, non-grid-converged reference."""

    if not isinstance(value, Mapping):
        return False
    expected = value.get("reference_npz_sha256_expected")
    observed = value.get("reference_npz_sha256_observed")
    record_sha = value.get("reference_record_sha256")
    commit = value.get("reference_record_source_commit_full_sha")
    return bool(
        value.get("reference_binding_verified") is True
        and value.get("reference_record") == P1_TERMINAL_REFERENCE_RECORD
        and isinstance(record_sha, str)
        and SHA256_RE.fullmatch(record_sha) is not None
        and isinstance(commit, str)
        and FULL_SHA_RE.fullmatch(commit) is not None
        and isinstance(expected, str)
        and SHA256_RE.fullmatch(expected) is not None
        and observed == expected
        and value.get("reference_grid_converged") is False
    )


def _terminal_reference_evidence(
    payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    measurements = _measurements(payload)
    physical = measurements.get("physical_field_reconstruction")
    physical = physical if isinstance(physical, Mapping) else {}
    planes = physical.get("selected_plane_full3d_comparison")
    planes = planes if isinstance(planes, Mapping) else {}
    full3d = measurements.get("full3d_reference_comparison")
    full3d = full3d if isinstance(full3d, Mapping) else {}
    evidence = {
        "reference_binding_verified": planes.get("reference_binding_verified"),
        "reference_record": planes.get("reference_record"),
        "reference_record_sha256": planes.get("reference_record_sha256"),
        "reference_record_source_commit_full_sha": planes.get(
            "reference_record_source_commit_full_sha"
        ),
        "reference_npz_sha256_expected": planes.get(
            "reference_npz_sha256_expected"
        ),
        "reference_npz_sha256_observed": planes.get(
            "reference_npz_sha256_observed"
        ),
        "reference_grid_converged": full3d.get("reference_grid_converged"),
    }
    if (
        full3d.get("reference_file") != evidence["reference_record"]
        or full3d.get("reference_commit_sha")
        != evidence["reference_record_source_commit_full_sha"]
        or not is_exact_p1_terminal_reference_evidence(evidence)
    ):
        return None
    return evidence


def is_exact_p1_h5_modal_basis_capacity(capacity: Any) -> bool:
    """Return whether ``capacity`` is the one frozen p1/h5 finite-spectrum limit."""

    if not isinstance(capacity, Mapping):
        return False
    first_rejected = _complex(
        capacity.get("first_rejected_numerical_infinity_beta_per_nm")
    )
    return bool(
        capacity.get("status") == "insufficient_finite_admissible_modes"
        and capacity.get("direction") == "positive"
        and capacity.get("requested_modes_per_direction") == 160
        and capacity.get("delivered_finite_admissible_modes") == 120
        and capacity.get("finite_candidate_count_both_directions") == 240
        and capacity.get("numerically_infinite_candidate_count") == 80
        and _finite(capacity.get("finite_spectrum_abs_beta_h_cutoff")) == 1.0e4
        and _finite(
            capacity.get("finite_spectrum_abs_beta_cutoff_per_nm")
        )
        == 2.0e3
        and capacity.get("leading_coefficient_singular_by_design") is True
        and capacity.get("pair_tolerance_relaxed") is False
        and _finite(capacity.get("left_pair_relative_error_tolerance")) == 1.0e-7
        and first_rejected is not None
        and abs(first_rejected) > 1.0e6
    )


def is_controlled_p1_h5_capacity_funnel(payload: Any) -> bool:
    """Recognize only the aggregate built from the exact p1/h5 capacity negative."""

    if not isinstance(payload, Mapping):
        return False
    identity = payload.get("identity")
    case = payload.get("case")
    qualification = payload.get("qualification")
    if not all(
        isinstance(value, Mapping)
        for value in (identity, case, qualification)
    ):
        return False
    return bool(
        payload.get("status") == "not_qualified"
        and identity.get("is_pde_run") is True
        and identity.get("is_solver_pass") is False
        and identity.get("is_mode_convergence_measurement") is True
        and identity.get("tracked_source_clean") is True
        and case.get("degree") == 1
        and _finite(case.get("h_nm")) == 5.0
        and case.get("primary_solver_path") == "modal-schur-memory-minimal"
        and case.get("mode_counts") == [80, 120, 160]
        and qualification.get("mode_count_converged") is False
        and qualification.get("selected_mode_count_per_direction") is None
        and qualification.get("selected_pair_strong") is False
        and qualification.get("all_sources_same_clean_sha") is True
        and qualification.get("all_external_watchdogs_pass") is True
        and qualification.get("modal_basis_capacity_limited") is True
        and payload.get("failures") == [P1_H5_CAPACITY_FAILURE]
        and is_exact_p1_h5_modal_basis_capacity(
            payload.get("modal_basis_capacity")
        )
    )


def is_controlled_p1_terminal_physical_funnel(payload: Any) -> bool:
    """Recognize a non-promoted p1 M160 physical-gate aggregate."""

    if not isinstance(payload, Mapping):
        return False
    identity = payload.get("identity")
    case = payload.get("case")
    qualification = payload.get("qualification")
    individual = payload.get("individual_gates")
    if not all(
        isinstance(value, Mapping)
        for value in (identity, case, qualification, individual)
    ):
        return False
    terminal = individual.get("160")
    terminal = terminal if isinstance(terminal, Mapping) else {}
    terminal_gate_contract = bool(
        terminal.get("integration_pass") is False
        and terminal.get("algebraic_chain_pass") is True
        and terminal.get("physical_field_gates_pass") is False
        and terminal.get("task033_physical_truncation_allowed") is True
        and terminal.get("candidate_pool_is_twice_requested_modes") is True
        and terminal.get("true_relative_residual_le_1e-9") is True
        and terminal.get("all_reported_gates_pass") is False
        and _finite(terminal.get("true_relative_residual")) is not None
        and _finite(terminal.get("true_relative_residual")) <= 1.0e-9
    )
    return bool(
        payload.get("status") == "not_qualified"
        and identity.get("is_pde_run") is True
        and identity.get("is_solver_pass") is False
        and identity.get("is_mode_convergence_measurement") is True
        and identity.get("tracked_source_clean") is True
        and case.get("degree") == 1
        and _finite(case.get("h_nm")) in {3.0, 2.5, 2.0, 1.5}
        and case.get("bottom_interface_nm") == 10.0
        and case.get("top_interface_nm") == 110.0
        and case.get("graded_reference_h_nm") is None
        and case.get("primary_solver_path") == "modal-schur-memory-minimal"
        and case.get("mode_counts") == [80, 120, 160]
        and qualification.get("mode_count_converged") is False
        and qualification.get("selected_mode_count_per_direction") is None
        and qualification.get("selected_pair_strong") is False
        and qualification.get("all_sources_same_clean_sha") is True
        and qualification.get("all_external_watchdogs_pass") is True
        and qualification.get("modal_basis_capacity_limited") is False
        and qualification.get("terminal_physical_gate_limited") is True
        and payload.get("modal_basis_capacity") is None
        and payload.get("failures") == [P1_TERMINAL_PHYSICAL_FAILURE]
        and terminal_gate_contract
        and is_exact_p1_terminal_reference_evidence(
            payload.get("terminal_physical_reference_evidence")
        )
    )


def _identity(payload: Mapping[str, Any]) -> tuple[Any, ...]:
    case = _case(payload)
    return (
        int(case.get("degree", -1)),
        _finite(case.get("h_nm")),
        _finite(case.get("wavelength_nm")),
        _finite(case.get("incident_grazing_deg")),
        str(case.get("polarization_kind")),
        _finite(case.get("bottom_interface_nm")),
        _finite(case.get("top_interface_nm")),
        case.get("graded_reference_h_nm"),
        case.get("graded_plan_hash"),
        _measurements(payload).get("hybrid_system", {}).get("primary_solver_path")
        if isinstance(_measurements(payload).get("hybrid_system"), Mapping)
        else None,
    )


def _mode_count(payload: Mapping[str, Any]) -> int | None:
    value = _case(payload).get("requested_modes_per_direction")
    return int(value) if type(value) is int and value > 0 else None


def _order_comparison(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    first = {
        key: row
        for row in _orders(previous)
        if (key := _order_key(row)) is not None
    }
    second = {
        key: row
        for row in _orders(current)
        if (key := _order_key(row)) is not None
    }
    if set(first) != set(second) or not first:
        return {
            "available": False,
            "coverage_equal": set(first) == set(second),
            "all_mandatory_gates_pass": False,
            "all_strong_gates_pass": False,
            "rows": [],
        }
    rows: list[dict[str, Any]] = []
    for key in sorted(first):
        old = first[key]
        new = second[key]
        if old.get("propagating") is not True or new.get("propagating") is not True:
            continue
        old_amp = _complex(old.get("outgoing_amplitude_at_boundary"))
        new_amp = _complex(new.get("outgoing_amplitude_at_boundary"))
        old_power = _finite(old.get("power_ratio"))
        new_power = _finite(new.get("power_ratio"))
        if old_amp is None or new_amp is None or old_power is None or new_power is None:
            rows.append({"key": list(key), "complete": False, "mandatory_pass": False})
            continue
        amp_delta = abs(new_amp - old_amp)
        amp_scale = max(abs(new_amp), abs(old_amp), 1.0e-30)
        power_delta = abs(new_power - old_power)
        power_scale = max(abs(new_power), abs(old_power), 1.0e-30)
        significant = power_scale >= SIGNIFICANT_ORDER_POWER
        amp_relative = amp_delta / amp_scale
        power_relative = power_delta / power_scale
        mandatory = (
            max(amp_relative, power_relative) <= MANDATORY_ORDER_RELATIVE_TOLERANCE
            if significant
            else max(amp_delta, power_delta) <= WEAK_ORDER_ABSOLUTE_TOLERANCE
        )
        strong = (
            max(amp_relative, power_relative) <= STRONG_ORDER_RELATIVE_TOLERANCE
            if significant
            else max(amp_delta, power_delta) <= WEAK_ORDER_ABSOLUTE_TOLERANCE
        )
        rows.append(
            {
                "key": list(key),
                "complete": True,
                "significant": significant,
                "previous_power_ratio": old_power,
                "current_power_ratio": new_power,
                "power_absolute_delta": power_delta,
                "power_relative_delta": power_relative,
                "complex_amplitude_absolute_delta": amp_delta,
                "complex_amplitude_relative_delta": amp_relative,
                "mandatory_pass": mandatory,
                "strong_pass": strong,
            }
        )
    return {
        "available": bool(rows),
        "coverage_equal": True,
        "propagating_order_count": len(rows),
        "significant_order_count": sum(item.get("significant") is True for item in rows),
        "max_significant_power_relative_delta": max(
            (
                float(item["power_relative_delta"])
                for item in rows
                if item.get("significant") is True and item.get("complete") is True
            ),
            default=0.0,
        ),
        "max_significant_complex_amplitude_relative_delta": max(
            (
                float(item["complex_amplitude_relative_delta"])
                for item in rows
                if item.get("significant") is True and item.get("complete") is True
            ),
            default=0.0,
        ),
        "all_mandatory_gates_pass": bool(rows)
        and all(item.get("mandatory_pass") is True for item in rows),
        "all_strong_gates_pass": bool(rows)
        and all(item.get("strong_pass") is True for item in rows),
        "rows": rows,
    }


def _pair_comparison(
    previous_m: int,
    previous: Mapping[str, Any],
    current_m: int,
    current: Mapping[str, Any],
) -> dict[str, Any]:
    previous_power = _port_power(previous)
    current_power = _port_power(current)
    totals: dict[str, float | None] = {}
    for key in ("R_total", "T_total", "A_balance"):
        old = _finite(previous_power.get(key))
        new = _finite(current_power.get(key))
        totals[key] = None if old is None or new is None else abs(new - old)
    complete = all(value is not None for value in totals.values())
    maximum = max((float(value) for value in totals.values() if value is not None), default=None)
    orders = _order_comparison(previous, current)
    current_gates = _individual_physical_gates(current)
    mandatory = bool(
        complete
        and maximum is not None
        and maximum <= MANDATORY_TOTAL_TOLERANCE
        and orders["all_mandatory_gates_pass"]
        and all(
            current_gates[key]
            for key in (
                "integration_pass",
                "algebraic_chain_pass",
                "physical_field_gates_pass",
                "task033_physical_truncation_allowed",
                "true_relative_residual_le_1e-9",
                "all_reported_gates_pass",
            )
        )
    )
    strong = bool(
        mandatory
        and maximum is not None
        and maximum <= STRONG_TOTAL_TOLERANCE
        and orders["all_strong_gates_pass"]
    )
    return {
        "previous_mode_count": previous_m,
        "current_mode_count": current_m,
        "absolute_total_deltas": totals,
        "max_absolute_total_delta": maximum,
        "diffraction_orders": orders,
        "current_individual_gates": current_gates,
        "mandatory_convergence_pass": mandatory,
        "strong_convergence_pass": strong,
    }


def build_hybrid_funnel(
    shards: Sequence[Mapping[str, Any]],
    *,
    source_descriptors: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate M80/M120/M160 (and conditional M240) summaries."""

    problems: list[str] = []
    by_m: dict[int, Mapping[str, Any]] = {}
    for payload in shards:
        mode_count = _mode_count(payload)
        if mode_count is None or mode_count in by_m:
            problems.append("mode counts are missing or duplicated")
            continue
        by_m[mode_count] = payload
    observed_modes = sorted(by_m)
    if observed_modes not in ([80, 120, 160], [80, 120, 160, 240]):
        problems.append("Task033 funnel requires exactly M80/M120/M160 and optional M240")

    identities = {_identity(payload) for payload in by_m.values()}
    if len(identities) != 1:
        problems.append("funnel shards do not describe one identical physical case")
    source_shas = {_source_sha(payload) for payload in by_m.values()}
    if None in source_shas or len(source_shas) != 1:
        problems.append("funnel shards do not share one full source SHA")
    if not all(_source_clean(payload) for payload in by_m.values()):
        problems.append("one or more funnel shards lack clean tracked-source evidence")
    if not all(_external_watchdog_pass(payload) for payload in by_m.values()):
        problems.append("one or more funnel shards failed the external watchdog contract")

    individual = {
        str(mode): _individual_physical_gates(payload)
        for mode, payload in sorted(by_m.items())
    }
    required_physical_gate_names = (
        "integration_pass",
        "algebraic_chain_pass",
        "physical_field_gates_pass",
        "task033_physical_truncation_allowed",
        "candidate_pool_is_twice_requested_modes",
        "true_relative_residual_le_1e-9",
        "all_reported_gates_pass",
    )
    individual_contracts_pass = all(
        all(individual[str(mode)][key] for key in required_physical_gate_names)
        or (
            mode in (80, 120)
            and _controlled_physical_truncation_negative(payload)
        )
        or (mode == 160 and _controlled_modal_basis_capacity_negative(payload))
        or (mode == 160 and _controlled_p1_terminal_physical_negative(payload))
        for mode, payload in by_m.items()
    )
    if not individual_contracts_pass:
        problems.append("one or more individual Hybrid physical/algebraic gates failed")

    comparisons = [
        _pair_comparison(first, by_m[first], second, by_m[second])
        for first, second in zip(observed_modes[:-1], observed_modes[1:], strict=True)
        if first in by_m and second in by_m
    ]
    pair_120_160 = next(
        (
            item
            for item in comparisons
            if item["previous_mode_count"] == 120
            and item["current_mode_count"] == 160
        ),
        None,
    )
    pair_160_240 = next(
        (
            item
            for item in comparisons
            if item["previous_mode_count"] == 160
            and item["current_mode_count"] == 240
        ),
        None,
    )
    selected_m: int | None = None
    convergence_pair: Mapping[str, Any] | None = None
    capacity_limited_m160 = bool(
        160 in by_m
        and _controlled_modal_basis_capacity_negative(by_m[160])
    )
    terminal_physical_limited_m160 = bool(
        160 in by_m
        and _controlled_p1_terminal_physical_negative(by_m[160])
    )
    if terminal_physical_limited_m160:
        problems.append(P1_TERMINAL_PHYSICAL_FAILURE)
    elif pair_120_160 is not None and pair_120_160["mandatory_convergence_pass"]:
        selected_m = 160
        convergence_pair = pair_120_160
    elif pair_160_240 is not None and pair_160_240["mandatory_convergence_pass"]:
        selected_m = 240
        convergence_pair = pair_160_240
    elif capacity_limited_m160:
        problems.append(P1_H5_CAPACITY_FAILURE)
    else:
        problems.append("M120->M160 did not converge and no qualifying M160->M240 result exists")

    all_sources_same_clean_sha = bool(
        len(source_shas) == 1
        and None not in source_shas
        and all(_source_clean(payload) for payload in by_m.values())
    )
    qualified = not problems and selected_m is not None
    identity = next(iter(identities), None)
    source_sha = next((value for value in source_shas if value is not None), None)
    capacity_evidence = (
        dict(_measurements(by_m[160]).get("modal_basis_capacity", {}))
        if capacity_limited_m160
        else None
    )
    terminal_reference_evidence = (
        _terminal_reference_evidence(by_m[160])
        if terminal_physical_limited_m160
        else None
    )
    return {
        "schema_version": "task033.case091.hybrid-funnel.v1",
        "record_type": "task033_hybrid_mode_truncation_funnel",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": "qualified" if qualified else "not_qualified",
        "identity": {
            "is_pde_run": bool(shards),
            "is_solver_pass": qualified,
            "is_mode_convergence_measurement": True,
            "ordinary_default_changed": False,
            "proves_0p7nm_feasible": False,
            "source_commit_full_sha": source_sha,
            "tracked_source_clean": all_sources_same_clean_sha,
        },
        "case": {
            "degree": None if identity is None else identity[0],
            "h_nm": None if identity is None else identity[1],
            "wavelength_nm": None if identity is None else identity[2],
            "incident_grazing_deg": None if identity is None else identity[3],
            "polarization_kind": None if identity is None else identity[4],
            "bottom_interface_nm": None if identity is None else identity[5],
            "top_interface_nm": None if identity is None else identity[6],
            "graded_reference_h_nm": None if identity is None else identity[7],
            "graded_plan_hash": None if identity is None else identity[8],
            "primary_solver_path": None if identity is None else identity[9],
            "mode_counts": observed_modes,
        },
        "tolerances": {
            "mandatory_total_absolute": MANDATORY_TOTAL_TOLERANCE,
            "strong_total_absolute": STRONG_TOTAL_TOLERANCE,
            "mandatory_significant_order_relative": MANDATORY_ORDER_RELATIVE_TOLERANCE,
            "strong_significant_order_relative": STRONG_ORDER_RELATIVE_TOLERANCE,
            "significant_order_power": SIGNIFICANT_ORDER_POWER,
            "weak_order_absolute": WEAK_ORDER_ABSOLUTE_TOLERANCE,
            "full_true_residual": 1.0e-9,
            "sampled_interface_E_relative": 5.0e-3,
            "sampled_interface_H_relative": 1.0e-2,
        },
        "source_records": list(source_descriptors or []),
        "individual_gates": individual,
        "comparisons": comparisons,
        "modal_basis_capacity": capacity_evidence,
        "terminal_physical_reference_evidence": (
            terminal_reference_evidence
        ),
        "qualification": {
            "mode_count_converged": qualified,
            "selected_mode_count_per_direction": selected_m,
            "selected_pair_strong": bool(
                convergence_pair is not None
                and convergence_pair.get("strong_convergence_pass") is True
            ),
            "all_sources_same_clean_sha": all_sources_same_clean_sha,
            "all_external_watchdogs_pass": all(
                _external_watchdog_pass(payload) for payload in by_m.values()
            ),
            "modal_basis_capacity_limited": capacity_limited_m160,
            "terminal_physical_gate_limited": (
                terminal_physical_limited_m160
            ),
        },
        "failures": problems,
        "limitations": [
            "This record qualifies modal truncation only for the stated p/h/interface case.",
            "It does not transfer accuracy to 0.7 nm or qualify a scalable generic modal core.",
            "M80 is an executed funnel point, not an independently sufficient physical pass.",
        ],
    }


def build_hybrid_funnel_from_paths(paths: Sequence[Path]) -> dict[str, Any]:
    payloads: list[dict[str, Any]] = []
    descriptors: list[dict[str, Any]] = []
    for requested in paths:
        path = Path(requested).resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{path} must contain a JSON object")
        payloads.append(payload)
        descriptors.append(
            {
                "path": str(path),
                "sha256": _sha256(path),
                "mode_count_per_direction": _mode_count(payload),
                "source_commit_full_sha": _source_sha(payload),
                "data_identity": "measured_external_watchdog_summary",
            }
        )
    return build_hybrid_funnel(payloads, source_descriptors=descriptors)
