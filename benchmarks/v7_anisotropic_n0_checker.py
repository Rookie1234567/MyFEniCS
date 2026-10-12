"""Additional V7 full-solve scope checks; shared exact-p4/output gates stay active."""

import hashlib
import json
from pathlib import Path

import numpy as np

from src.runners.v7_n0_output_audit import (
    grouped_powers,
    validate_n0_keys,
    y_variation_observation,
)


def saved_observation_errors(directory, summary):
    """Recompute bounded observations from saved modal and complex-field data."""
    errors = []
    output = summary["v7_output_audit"]
    modal_bytes = (
        directory / "numerical_output/dtn_port_diffraction_orders_3d.json"
    ).read_bytes()
    rows = json.loads(modal_bytes)["orders"]
    validate_n0_keys(rows)
    if hashlib.sha256(modal_bytes).hexdigest() != output.get("modal_sha256"):
        errors.append("V7 modal observation hash mismatch")
    if grouped_powers(rows) != output.get("power_groups"):
        errors.append("V7 power groups/tail differ from saved modal powers")
    archive = Path(
        summary["official_result"]["field_export"]["full3d_reference_archive"]
    )
    with np.load(archive, allow_pickle=False) as data:
        observed = y_variation_observation(
            data["E_V_per_m"], data["H_A_per_m"], data["y_nm"]
        )
    if observed != output.get("y_diagnostics"):
        errors.append("V7 y diagnostics differ from saved complex samples")
    curl = output["curl_samples"]
    curl_path = Path(curl["path"])
    if hashlib.sha256(curl_path.read_bytes()).hexdigest() != curl.get("sha256"):
        errors.append("V7 curl sample hash mismatch")
    with np.load(curl_path, allow_pickle=False) as data:
        values = data["curl_E_code_per_nm"]
        if not np.iscomplexobj(values) or not np.isfinite(values).all():
            errors.append("V7 curl samples are nonfinite or not complex")
    future = (
        output["power_groups"]["tail20_power"] <= 1e-5
        and output["same_field_truncation"]["delta20"] <= 1e-7
    )
    if output.get("future_A84_candidate_screen") is not bool(future):
        errors.append("V7 future A84 screen disagrees with observed tail/action")
    return errors


def v7_contract_errors(summary):
    errors = []

    def require(ok, message):
        if not ok:
            errors.append(message)

    require(
        summary.get("experiment") == "V7_ANISOTROPIC_N0_P4_FULL"
        and summary.get("execution_mode") == "full_solve"
        and summary.get("complete_solve") is True,
        "V7 requires a completed full solve, not a pilot",
    )
    require(
        summary.get("operator_scope") == "n0_filtered_dtn_not_full_dtn",
        "V7 filtered operator scope missing",
    )
    profile = summary.get("profile", {})
    require(
        profile.get("execution_mode") == "full_solve"
        and profile.get("outer", {}).get("planned_stop_iteration") is None,
        "V7 inherited a pilot stop",
    )
    require(
        profile.get("resources", {}).get("rss_hard_limit_bytes") == 1950000000000,
        "V7 RSS hard gate differs from 1.95 TB",
    )
    runtime = summary.get("retained_runtime", {})
    coarse = runtime.get("coarse_operator", {})
    require(
        coarse.get("degree") == 4
        and coarse.get("name") == "A4"
        and coarse.get("residual_scope") == "A4_n0"
        and coarse.get("relative_residual_limit") == 1e-10
        and coarse.get("maximum_extra_same_factor_refinements") == 2,
        "V7 exact A4_n0 contract differs",
    )
    selection = summary.get("operator_selection", {})
    require(
        selection.get("active_mode_count") == runtime.get("mode_count") == 572
        and selection.get("parent_mode_count") == 32060
        and selection.get("quadrature_inventory") == "full_parent_modes",
        "V7 active/parent inventory mismatch",
    )
    require(
        selection.get("active_mode_sha256")
        == runtime.get("mode_sha256")
        == "946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b"
        and selection.get("parent_mode_sha256")
        == "7f023c73d7b63379955642dd062e47ba7004f3cdf0accf42684286c4af71dbfb",
        "V7 live mode identities differ",
    )
    mesh = summary.get("v7_mesh_qa", {})
    require(
        mesh.get("status") == "PASS" and mesh.get("actual_global_cell_count") == 46800,
        "V7 actual mesh QA or 46800-cell contract is absent",
    )
    require(
        mesh.get("actual_axis_cell_counts") == [100, 2, 234]
        and mesh.get("jacobian", {}).get("all_positive") is True
        and mesh.get("jacobian", {}).get("minimum", 0.0) > 0.0
        and mesh.get("cell_tag_y_invariance", {}).get(
            "tags_constant_for_each_xz_column"
        )
        is True,
        "V7 actual anisotropic axes/Jacobian/y-tag evidence is absent",
    )
    require(
        all(
            summary.get("n0_functional_preparation", {})
            .get(str(degree), {})
            .get("dtn_quadrature_degree")
            == 160
            for degree in (6, 4)
        ),
        "V7 p6/p4 surface quadrature differs from parent q160",
    )
    require(
        summary.get("solve", {}).get("physical_residual_key") == "A6_n0_relative",
        "V7 residual must be named A6_n0",
    )
    require(
        all(
            summary.get(key, {}).get("operator_scope") == "A6_n0"
            for key in ("pre_release_a6", "post_release_a6", "residual_arrays")
        ),
        "V7 original-space residual artifacts lack A6_n0 scope",
    )
    require(
        summary.get("full_dtn_endpoint_check", {}).get("status")
        == "FULL_DTN_NOT_VERIFIED"
        and summary.get("full_dtn_endpoint_check", {}).get("A6_full_relative") is None,
        "V7 must not inherit old-mesh full DtN qualification",
    )
    output = summary.get("v7_output_audit", {})
    require(
        output.get("authority") == "AUTHORITY_LIMITED"
        and output.get("full_dtn_status") == "FULL_DTN_NOT_VERIFIED"
        and output.get("omitted_channel_values") == "NOT_COMPUTED",
        "V7 authority or omitted-channel scope is incorrect",
    )
    action = output.get("same_field_truncation", {})
    require(
        action.get("status") == "OBSERVED_NOT_A84_SOLUTION"
        and action.get("omitted_mode_count") == 488
        and action.get("retained_A84_count") == 84
        and action.get("new_factor_calls") == action.get("new_PDE_calls") == 0,
        "V7 same-field A84 observation is missing",
    )
    for value in (
        action.get("delta20"),
        action.get("b572_minus_A84_u572_relative"),
        output.get("power_groups", {}).get("tail20_power"),
    ):
        require(
            isinstance(value, (int, float)) and np.isfinite(value) and value >= 0,
            "V7 tail/action observation must be finite and nonnegative",
        )
    y = output.get("y_diagnostics", {})
    require(
        len(y.get("y_nm", [])) >= 4
        and y.get("phase_fitting") is False
        and y.get("threshold_role") == "diagnostic_warning_only",
        "V7 complex multi-y diagnostics are missing",
    )
    # These observations do not veto this solve if the proposed future truncation
    # or diagnostic symmetry warning fails its screening threshold.
    require(
        output.get("future_A84_screen_is_current_solve_gate") is False,
        "future truncation screening cannot qualify the present PDE",
    )
    return errors


def check_v7_anisotropic_n0_full(directory, summary):
    from benchmarks.physical_intermediate_checker import check_retained_v20

    checked = check_retained_v20(directory, summary, _v7_full=True)
    errors = checked["gate_failures"]
    errors.extend(v7_contract_errors(summary))
    try:
        errors.extend(saved_observation_errors(directory, summary))
        monitors = [
            json.loads(line)
            for line in (directory / "monitor_residuals.jsonl").read_text().splitlines()
            if line
        ]
        if not monitors or any(
            row.get("physical_residual_key") != "A6_n0_relative"
            or "original_A6_relative" in row
            for row in monitors
        ):
            errors.append("V7 monitor residual scope is not exclusively A6_n0")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"V7 scoped output evidence unavailable: {exc}")
    checked.update(
        classification=(
            "NUMERICAL_OR_OUTPUT_FAIL"
            if errors
            else "ANISOTROPIC_N0_DISCRETE_PASS_AUTHORITY_LIMITED"
        ),
        independent_output_gates_passed=not errors,
        reference_authority="AUTHORITY_LIMITED",
        full_dtn_status="FULL_DTN_NOT_VERIFIED",
        operator_scope="A6_n0",
    )
    return checked
