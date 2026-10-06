"""Pure corrupt-record tests; these synthetic samples are not FE evidence."""

from copy import deepcopy
import hashlib
import json

import numpy as np
import pytest

from src.postprocessing.neural_wave_audit import check_saved_arrays


NAMES = ("FIXED_WAVE_GREEDY_CONTROL", "LEARNED_WAVE_GREEDY")


def test_one_original_window_retains_full_field_and_save_reserve():
    from src.runners.neural_wave_campaign import stage_deadline

    allocation = {"deadline_monotonic": 172800 - 1800}
    campaign = {"deadline_monotonic": 172800}
    for route in NAMES:
        assert stage_deadline({"role": route}, allocation, campaign) == (
            172800 - 5400,
            5400,
        )
    assert stage_deadline({"role": "verify"}, allocation, campaign) == (
        172800 - 1800,
        1800,
    )
    earlier = {"deadline_monotonic": 10000}
    assert stage_deadline({"role": NAMES[0]}, earlier, campaign)[0] == 10000


def test_frozen_verifier_labels_excluded_from_both_training_routes():
    from src.io.neural_wave_campaign import ARTIFACTS, DESIGN, training_open_allowed

    design = json.loads(DESIGN.read_text())
    for name in (
        "v30_m5_verify",
        "v30_m5_saved_audit",
        "v30_m5_verify_final",
        "v30_m5_saved_audit_final",
    ):
        assert not training_open_allowed(ARTIFACTS / name / "result.json", design)


class SmallAction:
    a = dict(
        background_alpha=np.zeros(40, dtype=complex),
        background=np.zeros(3),
        total_g=np.ones(3),
        H=np.full(40, 2.0 / 1.04),
    )

    def apply(self, c):
        return np.array(c)

    def alpha(self, c):
        return np.ones(40, dtype=complex) * (1 + 0.2j)

    def audit(self, c):
        r = float(np.linalg.norm(c - np.ones(3)) / np.sqrt(3))
        return dict(
            native_relative=r,
            augmented_relative=r,
            original_total_augmented_relative=r,
            port_full_rhs_relative=0.0,
            port_operation_relative=0.0,
        )


def fixture():
    vector = np.array([[[1.0, 0.2j, -0.1]]], dtype=np.complex128)
    samples = dict(
        weights=np.ones((1, 1)),
        epsilon_imag=np.zeros(1),
        k0=np.array(1.0),
        mu_r=np.array(1 + 0j),
        incident_power=np.array(1.0),
        reference_c=np.ones(3),
        REFERENCE_independent_total_action=np.ones(3),
        background_E=np.zeros_like(vector),
        background_curl=np.zeros_like(vector),
        REFERENCE_E=vector.copy(),
        REFERENCE_curl=(1j * vector).copy(),
    )
    point = np.tile(vector[0], (6, 1))
    powers = np.zeros(40)
    powers[20] = 1
    record = dict(
        audit={"independent_DOLFINx_total_native_relative": 0.0},
        port={"R_total": 0.0, "T_total": 1.0, "A_balance": 0.0},
        volume={"A_volume_total": 0.0},
        selected_total_E=point,
        selected_scattered_E=point,
        selected_total_H_code=point,
        selected_scattered_H_code=point,
        ordered_per_channel_power=powers,
        status="PASS",
        qualified=True,
        official_candidate_results=True,
    )
    for kind in ("total", "scattered", "outgoing", "boundary_outgoing"):
        record["ordered_complex_" + kind + "_channels"] = np.ones(40, dtype=complex) * (
            1 + 0.2j
        )
    physics = dict(
        records={"REFERENCE": deepcopy(record)},
        ordered_mode_sides=["top"] * 20 + ["bottom"] * 20,
        ordered_incident_projection=np.zeros(40, dtype=complex),
        ordered_boundary_phase=np.ones(40, dtype=complex),
        ordered_mode_k_vectors=np.zeros((40, 3), dtype=complex),
        ordered_mode_e_vectors=np.tile([1.0, 0.0, 0.0], (40, 1)),
        port_area_nm2=2.0 / 1.04,
    )
    physics["ordered_mode_k_vectors"][20, 2] = -1.0
    physics["original_mode_manifest"] = dict(
        schema="fullspace-dtn.mode-manifest.v1",
        profile="full3d_scalable_v1",
        mode_count=40,
        modes=[
            dict(
                mode_index=i,
                side=physics["ordered_mode_sides"][i],
                m=i // 2,
                n=0,
                polarization="s" if i % 2 == 0 else "p",
                k_vector=physics["ordered_mode_k_vectors"][i].real.tolist(),
                e_vector=physics["ordered_mode_e_vectors"][i].tolist(),
            )
            for i in range(40)
        ],
    )
    mode_hash = hashlib.sha256(
        json.dumps(
            physics["original_mode_manifest"],
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    ).hexdigest()
    identity = dict(
        mode_manifest_sha256=mode_hash,
        model=dict(
            wavelength_nm=2 * np.pi,
            geometry=dict(bounds_nm=[[0, 2 / 1.04], [0, 1], [0, 1.04 / 2]]),
        ),
    )
    reconstruction = {}
    mpc_checks = {}
    for name in NAMES:
        physics["records"][name] = deepcopy(record)
        samples[name + "_E"] = vector.copy()
        samples[name + "_curl"] = (1j * vector).copy()
        samples[name + "_c"] = np.ones(3)
        samples[name + "_independent_total_action"] = np.ones(3)
        reconstruction[name] = dict(
            coefficient_q30_q60_relative=0.0,
            original_action_q30_q60_load_relative=0.0,
            FE_norm_q15_q30_relative=0.0,
            complete_model_mapping_relative=0.0,
            quadrature_pass=False,
        )
        mpc_checks[name] = 0.0
    return SmallAction(), physics, samples, reconstruction, mpc_checks, identity


def test_raw_checker_does_not_trust_pass_or_fail_labels():
    args = fixture()
    for r in args[1]["records"].values():
        r.update(status="FAIL", qualified=False)
    result = check_saved_arrays(*args)
    assert all(v["m5_full_discrete_numerical_gate"] for v in result["records"].values())
    args[2][NAMES[0] + "_E"][0, 0, 1] += 0.001j
    result = check_saved_arrays(*args)
    assert not result["records"][NAMES[0]]["field_pass"]
    assert not result["records"][NAMES[0]]["m5_full_discrete_numerical_gate"]
    assert result["records"][NAMES[1]]["m5_full_discrete_numerical_gate"]


@pytest.mark.parametrize(
    "damage", ["equation", "H", "mode", "power", "MPC", "quadrature", "mapping"]
)
def test_scientific_corruptions_cannot_keep_qualified(damage):
    action, physics, samples, reconstruction, mpc, identity = fixture()
    name = NAMES[0]
    if damage == "equation":
        samples[name + "_c"][1] += 0.001
        samples[name + "_independent_total_action"][1] += 0.001
    elif damage == "H":
        samples[name + "_curl"][0, 0, 0] += 0.001j
    elif damage == "mode":
        physics["records"][name]["ordered_complex_scattered_channels"][13] += 0.01j
    elif damage == "power":
        physics["records"][name]["ordered_per_channel_power"][0] = 2e-6
        physics["records"][name]["port"]["R_total"] = 2e-6
        physics["records"][name]["port"]["A_balance"] = -2e-6
    elif damage == "MPC":
        mpc[name] = 1.01e-10
    elif damage == "quadrature":
        reconstruction[name]["coefficient_q30_q60_relative"] = 1.01e-8
    elif damage == "mapping":
        reconstruction[name]["complete_model_mapping_relative"] = 1.01e-10
    if damage in ("power", "mode"):
        with pytest.raises(
            ValueError, match="POWER_NOT_FROM_ACTUAL|CHANNEL_DEFINITION"
        ):
            check_saved_arrays(action, physics, samples, reconstruction, mpc, identity)
        return
    result = check_saved_arrays(action, physics, samples, reconstruction, mpc, identity)
    assert not result["records"][name]["m5_full_discrete_numerical_gate"]


@pytest.mark.parametrize(
    "damage",
    [
        "missing_route",
        "wrong_mode_count",
        "negative_weight",
        "power_sum",
        "independent_action",
        "reference_channel",
        "mode_physics",
        "nonfinite_field",
    ],
)
def test_incomplete_or_inconsistent_original_data_rejected(damage):
    action, physics, samples, reconstruction, mpc, identity = fixture()
    if damage == "missing_route":
        del physics["records"][NAMES[1]]
    elif damage == "wrong_mode_count":
        physics["records"][NAMES[0]]["ordered_complex_total_channels"] = np.ones(39)
    elif damage == "negative_weight":
        samples["weights"][0, 0] = -1
    elif damage == "power_sum":
        physics["records"][NAMES[0]]["ordered_per_channel_power"][0] = 0.02
    elif damage == "independent_action":
        samples[NAMES[0] + "_independent_total_action"][2] += 0.01
    elif damage == "reference_channel":
        physics["records"]["REFERENCE"]["ordered_complex_total_channels"][0] += 0.01j
    elif damage == "mode_physics":
        physics["ordered_mode_k_vectors"][20, 2] *= -1
    elif damage == "nonfinite_field":
        samples["background_E"][0, 0, 0] = np.nan
    with pytest.raises(ValueError):
        check_saved_arrays(action, physics, samples, reconstruction, mpc, identity)
