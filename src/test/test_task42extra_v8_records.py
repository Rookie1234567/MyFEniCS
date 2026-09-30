"""Independent checker witnesses: forged passes and reference-exposed policies."""

from copy import deepcopy
import json
import os

import numpy as np
import pytest

from benchmarks.check_task42extra_v8 import (
    CHANNELS,
    physical_gate,
    phase_gate,
    common_work_points,
    power_inventory,
    own_pending_light,
)


def encoded(values):
    array = np.asarray(values, dtype=np.complex128)
    if array.ndim == 1:
        return [dict(real=float(x.real), imag=float(x.imag)) for x in array]
    return [encoded(row) for row in array]


def fixture(supervised=False):
    samples = np.full((6, 3), 0.2 + 0.3j)
    channels = np.full(40, 0.04 - 0.01j)
    audit = {
        key: 0.0
        for key in (
            "native_relative",
            "augmented_relative",
            "original_total_augmented_relative",
            "port_full_rhs_relative",
            "port_operation_relative",
            "independent_DOLFINx_total_native_relative",
            "slave_storage_max",
        )
    }
    audit["strict_pass"] = True
    reference = dict(
        audit=audit,
        port=dict(R_total=0.8, T_total=0.1, A_balance=0.1),
        volume=dict(A_volume_total=0.1),
        ordered_per_channel_power=[0.0] * 40,
    )
    errors = {}

    def pair(name, denominator):
        errors[name] = dict(absolute=0.0, denominator=float(denominator), relative=0.0)

    for kind, norms in (("total", [4.0, 5.0]), ("scattered", [2.0, 3.0])):
        reference[kind + "_L2_scaled_curl_norms"] = norms
        for quantity in ("E", "H"):
            reference[
                "selected_" + kind + "_" + ("H_code" if quantity == "H" else "E")
            ] = encoded(samples)
            name = "selected_" + kind + "_" + quantity
            pair(name, np.linalg.norm(samples))
            for j in range(6):
                pair(name + "_point_" + str(j), np.linalg.norm(samples[j]))
        for name, norm in zip(("L2", "scaled_curl"), norms, strict=True):
            pair(kind + "_" + name, norm)
    for name, field in CHANNELS.items():
        reference[field] = encoded(channels)
        pair(name, np.linalg.norm(channels))
    candidate = deepcopy(reference)
    comp = dict(
        errors=errors,
        numerical_reconstruction_pass=True,
        power_absolute_differences={
            key: 0.0 for key in ("R_total", "T_total", "A_balance", "A_volume")
        },
        max_channel_power_absolute=0.0,
        energy_closure_absolute=0.0,
        absorption_balance_volume_absolute=0.0,
    )
    row = dict(
        comparisons=comp,
        G_field_error=0.0,
        G_error_energy=0.0,
        G_reference_energy=4 + (2 * np.pi) ** 2 * 9,
        norm_identity=dict(
            G_energy=0.0,
            L2_energy=0.0,
            weighted_scaled_curl_energy=0.0,
            physical_energy=0.0,
            relative=0.0,
        ),
        reconstruction=dict(
            parameters_to_saved_c=dict(relative=0.0),
            next_quadrature_to_selected=dict(relative=0.0),
        ),
        reference_used_for_training=supervised,
        features_reference_exposed=supervised,
        pde_only_solve=not supervised,
        production_initialization_allowed=False,
        pde_only_solver_qualified=not supervised,
        official_candidate_results=not supervised,
        category="REPRESENTATION_WITNESS_POSITIVE"
        if supervised
        else "PDE_ONLY_SAME_P3_DISCRETE_PASS",
    )
    return row, candidate, reference


def test_complex_channel_denominator_is_recomputed():
    row, candidate, reference = fixture()
    candidate["ordered_complex_outgoing_channels"][0]["imag"] += 0.1
    with pytest.raises(ValueError, match="error/denominator"):
        physical_gate(row, candidate, reference, supervised=False, natural_scale=1)


def test_forged_equation_flag_is_not_a_pass():
    row, candidate, reference = fixture()
    candidate["audit"]["native_relative"] = 1e-3
    candidate["audit"]["strict_pass"] = True
    row["comparisons"]["numerical_reconstruction_pass"] = False
    row.update(
        category="PDE_OPTIMIZATION_NEGATIVE",
        pde_only_solver_qualified=False,
        official_candidate_results=False,
    )
    out = physical_gate(row, candidate, reference, supervised=False, natural_scale=1)
    assert not out["equation_pass"] and not out["pde_only_solver_qualified"]
    assert out["failed_equations"] == {"native_relative": 1e-3}


def test_supervised_fit_cannot_become_official_solver():
    row, candidate, reference = fixture(supervised=True)
    out = physical_gate(row, candidate, reference, supervised=True, natural_scale=1)
    assert out["numerical_reconstruction_pass"] and not out["pde_only_solver_qualified"]
    row["official_candidate_results"] = True
    with pytest.raises(ValueError, match="LABEL_POLICY"):
        physical_gate(row, candidate, reference, supervised=True, natural_scale=1)


def test_incomplete_complex_channel_inventory_is_rejected():
    row, candidate, reference = fixture()
    candidate["ordered_complex_total_channels"].pop()
    with pytest.raises(ValueError, match="40-channel"):
        physical_gate(row, candidate, reference, supervised=False, natural_scale=1)


def test_raw_energy_change_cannot_hide_in_saved_pass():
    row, candidate, reference = fixture()
    row["norm_identity"]["G_energy"] = 1
    with pytest.raises(ValueError, match="G_NORM_IDENTITY"):
        physical_gate(row, candidate, reference, supervised=False, natural_scale=1)


def test_nonzero_phase_derivatives_are_required():
    fe = dict(full_independent_complex_FE=31968, volume_and_DtN_degree=15)
    independent = dict(
        independent_64_node_Legendre_relative=0,
        custom_DOLFINx_relative=0,
        mpc_full_storage_relative=0,
        families={k: dict(norm=1, relative=0) for k in ("edge", "face", "interior")},
    )
    fe.update(
        independent_phase=independent,
        synthetic_nonunit_Floquet=dict(independent, nonunit_distance=2),
    )
    # Invalid derivatives fail before any saved "passed" string could help.
    ml = dict(
        initial_parameters_sha256="11d8cd454281fab85cfc59f04cee6aa7b864157d9f98513830947a0223d64103",
        initial_zero_scattered=True,
        k_zero=dict(relative=0),
        gradients={
            "phase": dict(batch={"c": dict(relative=0)}, directional_derivatives=[])
        },
    )
    with pytest.raises(ValueError, match="NONZERO_REAL"):
        phase_gate(fe, ml)


def test_same_wall_uses_latest_boundary_and_keeps_lag():
    def audit(seconds, count, loss):
        return dict(
            complete_closures=count,
            committed_complete_closures=count,
            loss=loss,
            native_relative=loss,
            augmented_relative=loss,
            checkpoint=dict(
                sha256=str(count), metadata=dict(elapsed_charged_seconds=seconds)
            ),
        )

    left = dict(
        audits=[audit(1, 0, 0.001), audit(5, 100, 1), audit(9, 200, 2)],
        launcher_charged_seconds=10,
        counts=dict(complete_closures=200),
        final_audit=dict(committed_complete_closures=200),
    )
    right = dict(
        audits=[audit(2, 0, 0.001), audit(7, 100, 3)],
        launcher_charged_seconds=8,
        counts=dict(complete_closures=100),
        final_audit=dict(committed_complete_closures=100),
    )
    result = common_work_points(left, right)
    assert result["common_wall_cap_seconds"] == 8
    assert (
        result["common_wall_latest_persisted_audits"]["plain"]["complete_closures"]
        == 100
    )
    assert (
        result["common_wall_latest_persisted_audits"]["plain"][
            "lag_from_common_cap_seconds"
        ]
        == 3
    )
    assert set(result["exact_common_committed_closure_points"]) == {"0", "100"}


def test_power_observable_must_equal_complete_mode_sum():
    modes = [
        dict(side="top" if j < 20 else "bottom", m=j % 20, n=0, polarization="s")
        for j in range(40)
    ]
    record = dict(
        ordered_per_channel_power=[0.04] * 20 + [0.005] * 20,
        port=dict(
            R_total=0.8,
            T_total=0.1,
            A_balance=0.1,
            R00_s=0.04,
            R00_p=0.0,
            R00_total=0.04,
        ),
    )
    power_inventory({"x": record}, modes)
    record["port"]["R_total"] = 0.7
    with pytest.raises(ValueError, match="POWER_SIDE_SUM"):
        power_inventory({"x": record}, modes)


def test_foreign_incomplete_light_summary_cannot_be_ignored(tmp_path):
    folder = tmp_path / "supervision"
    folder.mkdir()
    (folder / "resources.jsonl").write_text(
        json.dumps(dict(root_pid=-1, rss_bytes=1, swap_bytes=0)) + "\n"
    )
    with pytest.raises(ValueError, match="INCOMPLETE_OTHER_LIGHT"):
        own_pending_light(tmp_path)


def test_own_live_light_is_pending_not_claimed_complete(tmp_path):
    folder = tmp_path / "supervision"
    folder.mkdir()
    (folder / "resources.jsonl").write_text(
        json.dumps(dict(root_pid=os.getpid(), rss_bytes=1, swap_bytes=0)) + "\n"
    )
    row = own_pending_light(tmp_path)
    assert row["status"] == "OWN_CURRENT_LIGHT_SUMMARY_PENDING"
    assert "descendants_cleared" not in row
