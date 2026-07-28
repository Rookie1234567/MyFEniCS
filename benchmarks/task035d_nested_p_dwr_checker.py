"""Independent compact-evidence checker for Task035d nested-p DWR."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


_PERIODIC_P_DOWN_BUDGET_THRESHOLDS = (
    0.1,
    0.25,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
)
_CONSERVATIVE_PERIODIC_P_DOWN_BUDGET = 0.25


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _number(value: Any) -> float | None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        return None
    return float(value)


def _complex_pair(value: Any) -> complex | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    real = _number(value[0])
    imag = _number(value[1])
    if real is None or imag is None:
        return None
    return complex(real, imag)


def _roundoff_equal(
    observed: float,
    expected: float,
    *,
    relative_tolerance: float = 2.0e-13,
    absolute_tolerance: float = 1.0e-30,
) -> bool:
    return math.isclose(
        observed,
        expected,
        rel_tol=relative_tolerance,
        abs_tol=absolute_tolerance,
    )


def _channel_label(channel: Mapping[str, Any]) -> str:
    prefix = "R" if str(channel["side"]) == "top" else "T"
    return (
        f"{prefix}({int(channel['m'])},{int(channel['n'])})_"
        f"{str(channel['polarization'])}"
    )


def _goal_label(
    channel: Mapping[str, Any],
    quantity: str,
) -> str:
    prefix = "R" if str(channel["side"]) == "top" else "T"
    return (
        f"{prefix}_m{int(channel['m'])}_n{int(channel['n'])}_"
        f"{str(channel['polarization'])}_{quantity}"
    )


def _expected_inventory(
    authority: Mapping[str, Any],
) -> tuple[set[str], set[str]]:
    rows = authority.get("channels")
    if not isinstance(rows, list) or len(rows) != 12:
        return set(), set()
    channels: set[str] = set()
    goals: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(
            row.get("channel"), dict
        ):
            return set(), set()
        channel = row["channel"]
        channels.add(_channel_label(channel))
        for quantity in (
            "power",
            "amplitude_real",
            "amplitude_imag",
        ):
            goals.add(_goal_label(channel, quantity))
    return channels, goals


def _residual_gate_pass(gate: Any) -> bool:
    if not isinstance(gate, dict):
        return False
    reduced = _number(
        gate.get("reduced_trace_dtn_relative_residual")
    )
    full = _number(
        gate.get("full_explicit_true_relative_residual")
    )
    return bool(
        gate.get("schema_version")
        == "task035d.primal-residual-gate.v1"
        and reduced is not None
        and full is not None
        and 0.0 <= reduced <= 1.0e-9
        and 0.0 <= full <= 1.0e-9
    )


def _goal_closure_pass(
    label: str,
    goal: Any,
    *,
    basis_channels: Mapping[str, Any],
    state_delta_l2_norm: float | None,
) -> bool:
    if not isinstance(goal, dict):
        return False
    metadata = goal.get("goal")
    if not isinstance(metadata, dict):
        return False
    try:
        channel_label = _channel_label(metadata)
        expected_label = _goal_label(
            metadata,
            str(metadata["quantity"]),
        )
    except (KeyError, TypeError, ValueError):
        return False
    channel = basis_channels.get(channel_label)
    if not isinstance(channel, dict) or expected_label != label:
        return False
    actual = _number(goal.get("actual_goal_delta_a_minus_b"))
    estimate = _number(goal.get("signed_dwr_estimate"))
    value_a = _number(goal.get("value_a"))
    value_b = _number(goal.get("value_b"))
    stored_error = _number(goal.get("signed_goal_closure_error"))
    stored_limit = _number(goal.get("goal_closure_limit"))
    stored_residual_bound = _number(
        goal.get("unit_adjoint_residual_error_bound")
    )
    stored_unexplained_bound = _number(
        goal.get("unexplained_residual_pairing_bound")
    )
    gamma = _complex_pair(goal.get("unit_adjoint_goal_scalar"))
    unexplained_pairing = _complex_pair(
        goal.get("unexplained_residual_complex_pairing")
    )
    residual_norm = _number(
        channel.get("adjoint_residual", {}).get("residual_norm")
    )
    global_pairing = _complex_pair(goal.get("global_complex_pairing"))
    components = goal.get("components")
    cells = goal.get("cell_contributions")
    if (
        actual is None
        or estimate is None
        or value_a is None
        or value_b is None
        or stored_error is None
        or stored_limit is None
        or stored_residual_bound is None
        or stored_unexplained_bound is None
        or gamma is None
        or unexplained_pairing is None
        or residual_norm is None
        or residual_norm < 0.0
        or state_delta_l2_norm is None
        or state_delta_l2_norm < 0.0
        or global_pairing is None
        or not isinstance(components, dict)
        or not isinstance(cells, list)
        or len(cells) != 134
    ):
        return False
    recomputed_actual = value_a - value_b
    recomputed_error = estimate - recomputed_actual
    residual_bound = (
        abs(gamma) * residual_norm * state_delta_l2_norm
    )
    unexplained_bound = abs(unexplained_pairing)
    roundoff = (
        512.0
        * math.ulp(1.0)
        * max(
            abs(value_a),
            abs(value_b),
            abs(recomputed_actual),
            abs(estimate),
            1.0,
        )
    )
    recomputed_limit = 8.0 * (
        residual_bound + unexplained_bound + roundoff
    )
    if not all(
        (
            _roundoff_equal(actual, recomputed_actual),
            _roundoff_equal(stored_error, recomputed_error),
            _roundoff_equal(
                stored_residual_bound,
                residual_bound,
            ),
            _roundoff_equal(
                stored_unexplained_bound,
                unexplained_bound,
            ),
            _roundoff_equal(stored_limit, recomputed_limit),
        )
    ):
        return False
    if abs(recomputed_error) > recomputed_limit:
        return False
    if abs(global_pairing.real - estimate) > (
        2.0e-13 + 5.0e-11 * max(abs(global_pairing), abs(estimate), 1.0e-30)
    ):
        return False
    component_values = [
        _complex_pair(component.get("complex_pairing"))
        if isinstance(component, dict)
        else None
        for component in components.values()
    ]
    if any(value is None for value in component_values):
        return False
    component_sum = sum(
        (value for value in component_values if value is not None),
        0.0 + 0.0j,
    )
    component_scale = max(
        abs(global_pairing),
        sum(
            abs(value)
            for value in component_values
            if value is not None
        ),
        1.0e-30,
    )
    if abs(global_pairing - component_sum) > (
        2.0e-13 + 5.0e-11 * component_scale
    ):
        return False
    cell_values = [
        _complex_pair(cell.get("complex_pairing"))
        if isinstance(cell, dict)
        else None
        for cell in cells
    ]
    if any(value is None for value in cell_values):
        return False
    leaves = [
        int(cell["canonical_leaf"])
        for cell in cells
        if isinstance(cell, dict)
        and isinstance(cell.get("canonical_leaf"), int)
    ]
    if sorted(leaves) != list(range(134)):
        return False
    cell_sum = sum(
        (value for value in cell_values if value is not None),
        0.0 + 0.0j,
    )
    cell_total = _complex_pair(
        components.get("cell_total", {}).get("complex_pairing")
    )
    if cell_total is None:
        return False
    cell_scale = max(
        abs(cell_sum),
        sum(
            abs(value)
            for value in cell_values
            if value is not None
        ),
        abs(cell_total),
        1.0e-30,
    )
    return abs(cell_sum - cell_total) <= (
        2.0e-13 + 5.0e-11 * cell_scale
    )


def _port_identity_pass(external: Any) -> bool:
    if not isinstance(external, dict):
        return False
    coarse = external.get("coarse_port_operator_audit")
    enriched = external.get("enriched_port_operator_audit")
    if not isinstance(coarse, dict) or not isinstance(enriched, dict):
        return False
    invariant_fields = (
        "schema_version",
        "trace_functional_count",
        "auxiliary_interior_columns_allocated",
        "interior_degree_may_affect_port_operator",
        "external_operator_content_sha256",
        "external_rhs_content_sha256",
        "content_identity_is_partition_bound",
        "content_identity_requires_same_mpi_ownership",
    )
    hashes = (
        coarse.get("external_operator_content_sha256"),
        coarse.get("external_rhs_content_sha256"),
        enriched.get("external_operator_content_sha256"),
        enriched.get("external_rhs_content_sha256"),
    )
    rhs_norm = _number(external.get("direct_rhs_a_minus_b_l2_norm"))
    rhs_a_norm = _number(external.get("rhs_a_l2_norm"))
    rhs_b_norm = _number(external.get("rhs_b_l2_norm"))
    stored_rhs_scale = _number(
        external.get("direct_rhs_a_minus_b_scale")
    )
    recomputed_rhs_scale = (
        None
        if (
            rhs_a_norm is None
            or rhs_a_norm < 0.0
            or rhs_b_norm is None
            or rhs_b_norm < 0.0
        )
        else max(rhs_a_norm, rhs_b_norm, 1.0e-30)
    )
    stored_rhs_limit = _number(
        external.get("direct_rhs_a_minus_b_limit")
    )
    recomputed_rhs_limit = (
        None
        if recomputed_rhs_scale is None
        else 5.0e-12 + 5.0e-11 * recomputed_rhs_scale
    )

    def qualified_roundoff(audit: dict[str, Any]) -> bool:
        ratio = _number(
            audit.get(
                "removed_active_interior_over_threshold_max"
            )
        )
        threshold = _number(
            audit.get("acceptance_threshold_max_abs")
        )
        checks = audit.get("checks")
        return bool(
            isinstance(checks, dict)
            and checks
            and all(checks.values())
            and ratio is not None
            and 0.0 <= ratio <= 1.0
            and threshold is not None
            and threshold > 0.0
        )

    return bool(
        coarse.get("pass") is True
        and enriched.get("pass") is True
        and qualified_roundoff(coarse)
        and qualified_roundoff(enriched)
        and all(coarse.get(field) == enriched.get(field) for field in invariant_fields)
        and all(
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
            for value in hashes
        )
        and external.get(
            "zero_delta_derived_from_independent_port_identity"
        )
        is True
        and rhs_norm is not None
        and stored_rhs_scale is not None
        and recomputed_rhs_scale is not None
        and _roundoff_equal(
            stored_rhs_scale,
            recomputed_rhs_scale,
        )
        and recomputed_rhs_limit is not None
        and stored_rhs_limit is not None
        and _roundoff_equal(
            stored_rhs_limit,
            recomputed_rhs_limit,
        )
        and rhs_norm <= recomputed_rhs_limit
        and _number(external.get("port_l2_norm")) == 0.0
        and _number(external.get("auxiliary_l2_norm")) == 0.0
    )


def _residual_partition_pass(partition: Any) -> bool:
    if not isinstance(partition, dict):
        return False
    unexplained = _number(
        partition.get("unexplained_residual_l2_norm")
    )
    effective_norm = _number(
        partition.get("effective_residual_l2_norm")
    )
    component_norm_sum = _number(
        partition.get("component_residual_l2_norm_sum")
    )
    stored_limit = _number(
        partition.get("unexplained_residual_limit")
    )
    component_norms = partition.get("component_l2_norms")
    if (
        unexplained is None
        or unexplained < 0.0
        or effective_norm is None
        or effective_norm < 0.0
        or component_norm_sum is None
        or component_norm_sum < 0.0
        or stored_limit is None
        or not isinstance(component_norms, dict)
        or set(component_norms)
        != {
            "coarse_solver_residual",
            "cell_total",
            "port",
            "auxiliary",
            "enriched_solver_correction",
        }
    ):
        return False
    numeric_component_norms = [
        _number(value) for value in component_norms.values()
    ]
    if any(
        value is None or value < 0.0
        for value in numeric_component_norms
    ):
        return False
    recomputed_component_sum = sum(
        value
        for value in numeric_component_norms
        if value is not None
    )
    scale = max(
        effective_norm,
        recomputed_component_sum,
        1.0e-30,
    )
    recomputed_limit = 5.0e-12 + 5.0e-11 * scale
    stored_relative = _number(
        partition.get("unexplained_residual_relative")
    )
    return bool(
        _roundoff_equal(
            component_norm_sum,
            recomputed_component_sum,
        )
        and _roundoff_equal(stored_limit, recomputed_limit)
        and stored_relative is not None
        and _roundoff_equal(
            stored_relative,
            unexplained / scale,
        )
        and unexplained <= recomputed_limit
        and partition.get(
            "unexplained_residual_added_back_as_component"
        )
        is False
    )


def _periodic_p_down_action_audit(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute absolute multi-goal budgets for y-periodic cell pairs."""

    failures: list[str] = []
    cell_block = report.get("cell_residuals")
    cell_block = cell_block if isinstance(cell_block, dict) else {}
    cell_records = cell_block.get("records")
    cell_records = cell_records if isinstance(cell_records, list) else []
    changed_leaves = {
        int(row["canonical_leaf"])
        for row in cell_records
        if (
            isinstance(row, dict)
            and isinstance(row.get("canonical_leaf"), int)
            and row.get("interior_degree_changed") is True
        )
    }
    marking = report.get("cell_multigoal_marking")
    marking = marking if isinstance(marking, dict) else {}
    ranked = marking.get("ranked_cells")
    ranked = ranked if isinstance(ranked, list) else []
    rows_by_leaf: dict[int, dict[str, Any]] = {}
    groups: dict[tuple[float, float, float, float], list[int]] = {}
    for raw in ranked:
        if not isinstance(raw, dict) or not isinstance(
            raw.get("canonical_leaf"), int
        ):
            failures.append("ranked_cell_identity")
            continue
        leaf = int(raw["canonical_leaf"])
        box = raw.get("box")
        if (
            leaf in rows_by_leaf
            or not isinstance(box, list)
            or len(box) != 6
            or any(_number(value) is None for value in box)
        ):
            failures.append("ranked_cell_box")
            continue
        rows_by_leaf[leaf] = raw
        if leaf not in changed_leaves:
            continue
        values = tuple(float(value) for value in box)
        key = (values[0], values[2], values[3], values[5])
        groups.setdefault(key, []).append(leaf)
    if set(rows_by_leaf) != set(range(134)):
        failures.append("ranked_cell_coverage")
    if len(changed_leaves) != 32 or len(groups) != 16:
        failures.append("changed_periodic_pair_inventory")

    goal_dwr = report.get("goal_dwr")
    goal_dwr = goal_dwr if isinstance(goal_dwr, dict) else {}
    goals = goal_dwr.get("goals")
    goals = goals if isinstance(goals, dict) else {}
    normalized_by_goal: dict[str, dict[int, float]] = {}
    endpoint_ratios: list[dict[str, Any]] = []
    for label, raw_goal in goals.items():
        if not isinstance(label, str) or not isinstance(raw_goal, dict):
            failures.append("goal_action_identity")
            continue
        tolerance = _number(
            raw_goal.get("unchanged_v0_absolute_tolerance")
        )
        actual_delta = _number(
            raw_goal.get("actual_goal_delta_a_minus_b")
        )
        contributions = raw_goal.get("cell_contributions")
        if (
            tolerance is None
            or tolerance <= 0.0
            or actual_delta is None
            or not isinstance(contributions, list)
        ):
            failures.append(f"goal_action_payload:{label}")
            continue
        by_leaf: dict[int, float] = {}
        for raw_cell in contributions:
            if not isinstance(raw_cell, dict) or not isinstance(
                raw_cell.get("canonical_leaf"), int
            ):
                failures.append(f"goal_action_cell_identity:{label}")
                continue
            leaf = int(raw_cell["canonical_leaf"])
            signed = _number(raw_cell.get("signed_real_contribution"))
            stored = _number(
                raw_cell.get("normalized_absolute_contribution")
            )
            if (
                leaf in by_leaf
                or signed is None
                or stored is None
                or stored < 0.0
                or not _roundoff_equal(
                    stored,
                    abs(signed) / tolerance,
                )
            ):
                failures.append(f"goal_action_cell_value:{label}")
                continue
            by_leaf[leaf] = stored
        if set(by_leaf) != set(range(134)):
            failures.append(f"goal_action_cell_coverage:{label}")
            continue
        normalized_by_goal[label] = by_leaf
        endpoint_ratios.append(
            {
                "goal": label,
                "absolute_delta_over_tolerance": (
                    abs(actual_delta) / tolerance
                ),
            }
        )
    if len(normalized_by_goal) != 36:
        failures.append("goal_action_inventory")

    pair_rows: list[dict[str, Any]] = []
    for key, leaves in groups.items():
        ordered = sorted(
            leaves,
            key=lambda leaf: float(rows_by_leaf[leaf]["box"][1]),
        )
        intervals = [
            (
                float(rows_by_leaf[leaf]["box"][1]),
                float(rows_by_leaf[leaf]["box"][4]),
            )
            for leaf in ordered
        ]
        if (
            len(ordered) != 2
            or intervals != [(0.0, 12.5), (12.5, 25.0)]
            or any(
                rows_by_leaf[leaf].get("interior_degree_changed")
                is not True
                for leaf in ordered
            )
        ):
            failures.append("periodic_pair_geometry")
            continue
        budgets = {
            label: sum(by_leaf[leaf] for leaf in ordered)
            for label, by_leaf in normalized_by_goal.items()
        }
        if not budgets:
            failures.append("periodic_pair_goal_budget")
            continue
        limiting_goal = max(budgets, key=budgets.get)
        maximum = budgets[limiting_goal]
        pair_rows.append(
            {
                "periodic_pair": ordered,
                "x_z_box": list(key),
                "limiting_goal": limiting_goal,
                "maximum_absolute_goal_budget": maximum,
                "eligible_at_conservative_budget": (
                    maximum
                    <= _CONSERVATIVE_PERIODIC_P_DOWN_BUDGET
                ),
            }
        )
    pair_rows.sort(
        key=lambda row: (
            float(row["maximum_absolute_goal_budget"]),
            row["periodic_pair"],
        )
    )
    endpoint_ratios.sort(
        key=lambda row: (
            -float(row["absolute_delta_over_tolerance"]),
            str(row["goal"]),
        )
    )
    eligible_counts = {
        str(threshold): sum(
            float(row["maximum_absolute_goal_budget"]) <= threshold
            for row in pair_rows
        )
        for threshold in _PERIODIC_P_DOWN_BUDGET_THRESHOLDS
    }
    checks = {
        "ranked_cell_coverage": set(rows_by_leaf) == set(range(134)),
        "changed_cell_count": len(changed_leaves) == 32,
        "periodic_pair_count": len(pair_rows) == 16,
        "goal_count": len(normalized_by_goal) == 36,
        "all_pair_rows_complete": (
            len(pair_rows) == 16
            and all(
                len(row["periodic_pair"]) == 2 for row in pair_rows
            )
        ),
    }
    failures.extend(
        name for name, passed in checks.items() if not passed
    )
    failures = list(dict.fromkeys(failures))
    conservative_eligible = eligible_counts[
        str(_CONSERVATIVE_PERIODIC_P_DOWN_BUDGET)
    ]
    return {
        "schema_version": "task035d.periodic-p-down-action-audit.v1",
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "absolute_budget_semantics": (
            "sum over both y-periodic cells of "
            "abs(signed cell DWR contribution) divided by each frozen "
            "unchanged-v0 goal tolerance; signed cancellation is forbidden"
        ),
        "conservative_per_goal_budget": (
            _CONSERVATIVE_PERIODIC_P_DOWN_BUDGET
        ),
        "eligible_pair_counts_by_budget": eligible_counts,
        "periodic_pairs": pair_rows,
        "endpoint_goal_count_over_one_tolerance": sum(
            float(row["absolute_delta_over_tolerance"]) > 1.0
            for row in endpoint_ratios
        ),
        "maximum_endpoint_delta": (
            endpoint_ratios[0] if endpoint_ratios else None
        ),
        "decision": (
            "p_down_candidate_available"
            if conservative_eligible
            else "controlled_stop_remote_p5_interior_no_safe_periodic_pair"
        ),
        "heavy_pde_authorized": conservative_eligible > 0,
    }


def task035d_nested_p_dwr_report_gate(
    report: Mapping[str, Any],
    significant_channel_authority: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute formal DWR status without trusting stored pass fields."""

    expected_channels, expected_goals = _expected_inventory(
        significant_channel_authority
    )
    goal_dwr = report.get("goal_dwr", {})
    goals = (
        goal_dwr.get("goals", {})
        if isinstance(goal_dwr, dict)
        else {}
    )
    basis = report.get("unit_channel_adjoint_basis", {})
    basis_channels = (
        basis.get("channels", {}) if isinstance(basis, dict) else {}
    )
    basis_goals = (
        basis.get("goals", {}) if isinstance(basis, dict) else {}
    )
    cell_block = report.get("cell_residuals", {})
    cell_records = (
        cell_block.get("records", ())
        if isinstance(cell_block, dict)
        else ()
    )
    canonical_leaves = [
        int(row["canonical_leaf"])
        for row in cell_records
        if isinstance(row, dict)
        and isinstance(row.get("canonical_leaf"), int)
    ]
    changed_cells = [
        row
        for row in cell_records
        if isinstance(row, dict)
        and row.get("interior_degree_changed") is True
    ]
    identity_checks_pass = bool(
        len(cell_records) == 134
        and all(
            isinstance(row, dict)
            and isinstance(row.get("identity_checks"), dict)
            and row.get("unchanged_cell_zero_delta_pass") is True
            and all(row["identity_checks"].values())
            for row in cell_records
        )
    )
    partition = report.get("residual_partition", {})
    primal = report.get("primal_endpoints", {})
    external_partition = report.get("external_partition", {})
    state_delta_l2_norm = _number(
        primal.get("state_delta_l2_norm")
        if isinstance(primal, dict)
        else None
    )
    action_audit = _periodic_p_down_action_audit(report)
    channel_residuals_pass = bool(
        set(basis_channels) == expected_channels
        and all(
            isinstance(row, dict)
            and _number(
                row.get("adjoint_residual", {}).get(
                    "relative_residual"
                )
            )
            is not None
            and 0.0
            <= float(
                row["adjoint_residual"]["relative_residual"]
            )
            <= 1.0e-9
            for row in basis_channels.values()
        )
    )
    goal_residuals_pass = bool(
        set(basis_goals) == expected_goals
        and all(
            isinstance(row, dict)
            and _number(
                row.get("scaled_adjoint_residual", {}).get(
                    "relative_residual"
                )
            )
            is not None
            and 0.0
            <= float(
                row["scaled_adjoint_residual"]["relative_residual"]
            )
            <= 1.0e-9
            for row in basis_goals.values()
        )
    )
    checks = {
        "report_schema": (
            report.get("schema_version")
            == "task035d.variable-p-nested-live-dwr.v1"
        ),
        "not_controlled_negative": (
            report.get("controlled_negative") is not True
        ),
        "authority_schema": (
            significant_channel_authority.get("schema_version")
            == "task035b.significant-channel-reference.v1"
            and significant_channel_authority.get("pass") is True
            and len(expected_channels) == 12
            and len(expected_goals) == 36
        ),
        "goal_inventory_exact": set(goals) == expected_goals,
        "all_goal_closures_recomputed": (
            len(goals) == 36
            and all(
                _goal_closure_pass(
                    label,
                    goal,
                    basis_channels=basis_channels,
                    state_delta_l2_norm=state_delta_l2_norm,
                )
                for label, goal in goals.items()
            )
        ),
        "unit_channel_residuals_recomputed": channel_residuals_pass,
        "scaled_goal_residuals_recomputed": goal_residuals_pass,
        "primal_residuals_recomputed": (
            isinstance(primal, dict)
            and _residual_gate_pass(
                primal.get("coarse_residual_gate")
            )
            and _residual_gate_pass(
                primal.get("enriched_residual_gate")
            )
        ),
        "residual_partition_recomputed": (
            _residual_partition_pass(partition)
        ),
        "port_identity_recomputed": (
            _port_identity_pass(external_partition)
        ),
        "cell_inventory_recomputed": (
            isinstance(cell_block, dict)
            and cell_block.get("dense_schur_persisted") is False
            and sorted(canonical_leaves) == list(range(134))
            and len(changed_cells) == 32
            and identity_checks_pass
        ),
        "frozen_goal_set_complete": (
            report.get("significant_channel_authority", {}).get(
                "selected_goal_set_complete_by_frozen_authority"
            )
            is True
        ),
        "periodic_p_down_action_audit": action_audit["pass"] is True,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task035d.nested-p-dwr-checker.v2",
        "contract_revision": "periodic-absolute-budget-v1",
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "recomputed_channel_count": len(expected_channels),
        "recomputed_goal_count": len(expected_goals),
        "stored_top_level_pass": report.get("pass"),
        "stored_goal_pass": (
            goal_dwr.get("pass")
            if isinstance(goal_dwr, dict)
            else None
        ),
        "periodic_p_down_action_audit": action_audit,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("significant_channel_authority", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    authority = json.loads(
        args.significant_channel_authority.read_text(encoding="utf-8")
    )
    gate = task035d_nested_p_dwr_report_gate(report, authority)
    gate["input_authorities"] = {
        "report": {
            "path": str(args.report),
            "sha256": _sha256(args.report),
        },
        "significant_channel_authority": {
            "path": str(args.significant_channel_authority),
            "sha256": _sha256(args.significant_channel_authority),
        },
    }
    encoded = json.dumps(gate, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.write_text(encoded, encoding="utf-8")
    return 0 if gate["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
