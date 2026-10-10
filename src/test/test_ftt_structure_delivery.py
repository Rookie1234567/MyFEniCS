"""Negative controls for final frozen-record decisions, with no model/PDE calls."""

from copy import deepcopy

import pytest

from benchmarks.check_ftt_structure_delivery import numerical_decision


def fixture(labelled=False):
    names = (
        {
            f"{field}_{kind}"
            for field in ("total", "scattered")
            for kind in ("E", "H_code", "curl")
        }
        | {
            f"selected_{field}_{kind}_{i}"
            for field in ("total", "scattered")
            for kind in ("E", "H_code")
            for i in range(6)
        }
        | {
            f"complex_{kind}_channels"
            for kind in ("total", "scattered", "outgoing", "boundary_outgoing")
        }
    )
    return dict(
        field_errors={
            key: dict(absolute=0, denominator=1, relative=0) for key in names
        },
        independent_total_native=dict(absolute=0, denominator=1, relative=0),
        equation_audit=dict(native_relative=0, augmented_relative=0),
        power_absolute_differences=dict(R_total=0, T_total=0, A_balance=0, A_volume=0),
        energy_closure=0,
        max_per_mode_power_absolute=0,
        reconstruction=dict(
            complete_model_mapping_relative=0,
            coefficient_q30_q60_relative=0,
            original_action_q30_q60_load_relative=0,
            FE_norm_q15_q30_relative=0,
        ),
        Gram_integral_pairing=dict(
            error_energy_pairing_relative=0,
            reference_energy_pairing_relative=0,
            G_error_energy=0,
            G_reference_energy=1,
            E_G=0,
        ),
        MPC_relative=0,
        port_recovery_relative=0,
        original_equation_pass=True,
        field_pass=True,
        power_pass=True,
        model_rebuild_pass=True,
        quadrature_pass=True,
        m5_full_discrete_numerical_gate=True,
        reference_used_for_training=labelled,
        features_reference_exposed=labelled,
        pde_only_solve=not labelled,
        production_initialization_allowed=False,
        official_candidate_results=False,
        pde_only_solver_qualified=not labelled,
    )


@pytest.mark.parametrize("labelled", [False, True])
def test_physical_numeric_pass_keeps_label_boundary(labelled):
    x = fixture(labelled)
    assert numerical_decision(x)["m5_full_discrete_numerical_gate"]
    assert x["pde_only_solver_qualified"] is not labelled


@pytest.mark.parametrize(
    "damage",
    [
        "native",
        "channel_denominator",
        "missing_sample",
        "fit_qualified",
        "model",
        "power",
    ],
)
def test_corruption_cannot_preserve_claimed_pass(damage):
    x = deepcopy(fixture(damage == "fit_qualified"))
    if damage == "native":
        x["equation_audit"]["native_relative"] = 0.01
    elif damage == "channel_denominator":
        x["field_errors"]["complex_scattered_channels"]["denominator"] = 0
    elif damage == "missing_sample":
        del x["field_errors"]["selected_scattered_E_5"]
    elif damage == "fit_qualified":
        x["pde_only_solver_qualified"] = True
    elif damage == "model":
        x["reconstruction"]["complete_model_mapping_relative"] = 0.01
    elif damage == "power":
        x["max_per_mode_power_absolute"] = 0.001
    with pytest.raises(ValueError):
        numerical_decision(x)
