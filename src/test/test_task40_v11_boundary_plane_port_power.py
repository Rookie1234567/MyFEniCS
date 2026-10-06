from __future__ import annotations

import csv
import json
from dataclasses import replace

from mpi4py import MPI
import numpy as np

from src.common.modes_3d import PortMode3D, incident_power_3d, outgoing_port_modes_3d
from src.runners.task40_v10_output_checker import verify_v10_dtn_port_mode_table
from src.solvers.dtn_boundary_phase_gauge import (
    BOUNDARY_PLANE,
    GLOBAL_Z,
    boundary_mode_power_from_solver,
    incident_projection_in_solver_coordinates,
    outgoing_solver_amplitudes,
)
from src.solvers.dtn_port_3d import (
    _mode_boundary_phase,
    _mode_power_at_boundary,
    _port_power_metrics,
    _write_port_outputs,
)
from src.test.stage2_test_utils import stage4_block_config


def _cfg(**updates):
    values = {
        "stage_case": "stage4_block_grating",
        "stage4_boundary_model": "dtn_port",
        "stage4_dtn_order_policy": "auto_propagating",
        "stage4_dtn_assembly": "auxiliary",
        "use_pml": False,
        "pml_top_thickness": 0.0,
        "pml_bottom_thickness": 0.0,
        "diffraction_zero_order_only": False,
    }
    values.update(updates)
    return stage4_block_config(**values)


def _complex_pair(value):
    return complex(float(value[0]), float(value[1]))


def _direct_cross_power(mode, cfg, amplitude, *, phase=None):
    electric = complex(amplitude) * mode.e_vector
    if phase is not None:
        electric = electric * phase
    magnetic = np.cross(mode.k_vector, electric) / (cfg.k0 * complex(cfg.mu_r))
    normal_sign = 1.0 if mode.side == "top" else -1.0
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    return float(0.5 * area * normal_sign * np.real(np.cross(electric, np.conj(magnetic))[2]))


def test_global_default_stays_legacy_and_plane_power_matches_independent_cross_product():
    cfg = _cfg()
    modes = outgoing_port_modes_3d(cfg)
    incident = np.asarray(
        [incident_projection_in_solver_coordinates(mode, cfg, GLOBAL_Z) for mode in modes],
        dtype=np.complex128,
    )
    outgoing = np.zeros(len(modes), dtype=np.complex128)
    power_carrying = [index for index, mode in enumerate(modes) if mode.power_per_unit_amplitude > 0]
    chosen = [index for index in power_carrying if modes[index].side == "top"][:1]
    chosen += [index for index in power_carrying if modes[index].side == "bottom"][:1]
    for index, value in zip(chosen, (0.23 + 0.17j, -0.31 + 0.09j), strict=True):
        outgoing[index] = value
    total = outgoing.copy()
    for index, mode in enumerate(modes):
        if mode.side == "top":
            total[index] += incident[index]

    legacy = _port_power_metrics(cfg, modes, total, incident)
    assert legacy["dtn_phase_gauge"] == GLOBAL_Z
    assert "top outgoing amplitude" in legacy["dtn_port_modal_amplitude_convention"]
    legacy_expected = {"top": 0.0, "bottom": 0.0}
    legacy_outgoing = outgoing_solver_amplitudes(total, incident, modes)
    for mode, amplitude in zip(modes, legacy_outgoing, strict=True):
        if mode.power_per_unit_amplitude > 0.0:
            legacy_expected[mode.side] += _mode_power_at_boundary(
                mode, cfg, amplitude
            ) / incident_power_3d(cfg)
    assert np.isclose(legacy["R_total"], legacy_expected["top"], rtol=0.0, atol=1e-14)
    assert np.isclose(legacy["T_total"], legacy_expected["bottom"], rtol=0.0, atol=1e-14)

    plane_incident = np.asarray(
        [incident_projection_in_solver_coordinates(mode, cfg, BOUNDARY_PLANE) for mode in modes],
        dtype=np.complex128,
    )
    plane_total = outgoing.copy()
    for index, mode in enumerate(modes):
        if mode.side == "top":
            plane_total[index] += plane_incident[index]
    plane_outgoing = outgoing_solver_amplitudes(plane_total, plane_incident, modes)
    plane = _port_power_metrics(
        cfg, modes, plane_total, plane_incident, dtn_phase_gauge=BOUNDARY_PLANE
    )
    expected_by_side = {"top": 0.0, "bottom": 0.0}
    for mode, amplitude in zip(modes, plane_outgoing, strict=True):
        if mode.power_per_unit_amplitude <= 0.0:
            continue
        helper = boundary_mode_power_from_solver(mode, cfg, amplitude, BOUNDARY_PLANE)
        s = _mode_boundary_phase(mode, cfg)
        global_amplitude = amplitude / s
        global_equivalent = boundary_mode_power_from_solver(mode, cfg, global_amplitude, GLOBAL_Z)
        assert np.isclose(helper, global_equivalent, rtol=2e-13, atol=1e-14)
        direct = _direct_cross_power(mode, cfg, amplitude)
        assert np.isclose(helper, direct, rtol=2e-13, atol=1e-14)
        expected_by_side[mode.side] += helper / incident_power_3d(cfg)
    assert np.isclose(plane["R_total"], expected_by_side["top"], rtol=0.0, atol=1e-14)
    assert np.isclose(plane["T_total"], expected_by_side["bottom"], rtol=0.0, atol=1e-14)


def test_boundary_plane_keeps_lossy_below_critical_bottom_mode_power():
    cfg = _cfg(incident_theta_deg=89.0)
    modes = outgoing_port_modes_3d(cfg)
    index = next(
        i for i, mode in enumerate(modes)
        if mode.side == "bottom" and mode.m == 0 and mode.n == 0
        and not mode.propagating and mode.power_per_unit_amplitude > 0.0
    )
    incident = np.asarray(
        [incident_projection_in_solver_coordinates(mode, cfg, BOUNDARY_PLANE) for mode in modes],
        dtype=np.complex128,
    )
    total = incident.copy()
    total[index] = 0.37 - 0.21j
    result = _port_power_metrics(
        cfg, modes, total, incident, dtn_phase_gauge=BOUNDARY_PLANE
    )
    outgoing = outgoing_solver_amplitudes(total, incident, modes)
    expected = boundary_mode_power_from_solver(
        modes[index], cfg, outgoing[index], BOUNDARY_PLANE
    ) / incident_power_3d(cfg)
    direct = _direct_cross_power(modes[index], cfg, outgoing[index])
    assert expected > 0.0
    assert np.isclose(expected, direct / incident_power_3d(cfg), rtol=2e-13, atol=1e-14)
    assert np.isclose(result["T_total"], expected, rtol=0.0, atol=1e-14)


def test_boundary_plane_writer_keeps_unrepresentable_global_optional_and_checks_npz(tmp_path):
    cfg = replace(_cfg(), z_min=-1.0e4, z_max=1.0e4)
    electric = np.asarray((1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j), dtype=np.complex128)
    modes = []
    for side, sign in (("top", 1), ("bottom", -1)):
        wavevector = np.asarray((0.0 + 0.0j, 0.0 + 0.0j, sign * 1.0j * 1000.0), dtype=np.complex128)
        magnetic = np.cross(wavevector, electric) / (cfg.k0 * complex(cfg.mu_r))
        modes.append(
            PortMode3D(
                side=side,
                m=1,
                n=0,
                polarization="s",
                alpha=0.0 + 0.0j,
                gamma=0.0 + 0.0j,
                beta=1.0j * 1000.0,
                refractive_index=1.0 + 0.0j,
                vertical_sign=sign,
                e_vector=electric,
                k_vector=wavevector,
                h_vector=magnetic,
                electric_tangential_norm_sq=1.0,
                power_per_unit_amplitude=0.0,
                propagating=False,
                rayleigh_warning=False,
            )
        )
    index = 0
    mode = modes[index]
    assert _mode_boundary_phase(mode, cfg) == 0.0j

    total = np.zeros(len(modes), dtype=np.complex128)
    incident = np.zeros(len(modes), dtype=np.complex128)
    total[index] = 0.75 - 0.25j
    metrics = _port_power_metrics(
        cfg, modes, total, incident, dtn_phase_gauge=BOUNDARY_PLANE
    )
    _write_port_outputs(
        tmp_path, cfg, modes, total, incident, metrics,
        MPI.COMM_SELF,
        dtn_phase_gauge=BOUNDARY_PLANE,
    )

    json_rows = json.loads((tmp_path / "dtn_auxiliary_amplitudes_3d.json").read_text())
    json_row = json_rows[index]
    assert json_row["dtn_phase_gauge"] == BOUNDARY_PLANE
    assert _complex_pair(json_row["solver_outgoing_amplitude"]) == total[index]
    assert _complex_pair(json_row["physical_boundary_outgoing_amplitude"]) == total[index]
    assert json_row["outgoing_amplitude"] is None
    assert json_row["global_output_representable"] is False
    assert json_row["global_output_failure_reason"]

    npz_path = tmp_path / "dtn_port_modal_amplitudes_3d.npz"
    with np.load(npz_path, allow_pickle=False) as arrays:
        assert arrays["solver_outgoing_amplitude"][index] == total[index]
        assert arrays["physical_boundary_outgoing_amplitude"][index] == total[index]
        assert np.isfinite(arrays["physical_boundary_outgoing_amplitude"][index])
        assert arrays["physical_boundary_outgoing_representable"][index]
        assert not arrays["legacy_global_outgoing_representable"][index]
        assert np.isnan(arrays["legacy_global_outgoing_amplitude"][index].real)
        assert not arrays["global_output_representable"][index]
        npz_values = {name: np.asarray(arrays[name]).copy() for name in arrays.files}

    table = verify_v10_dtn_port_mode_table(
        tmp_path / "dtn_port_diffraction_orders_3d.csv",
        expected_channel_count=len(modes),
    )
    assert table["passed"] is True
    assert table["modal_amplitudes_npz"]["json_csv_npz_values_agree"] is True

    # Negative fixture: a finite but inconsistent top outgoing value must fail
    # even though all NPZ arrays remain finite.
    npz_values["solver_outgoing_amplitude"][index] += 1.0
    npz_values["physical_boundary_outgoing_amplitude"][index] += 1.0
    np.savez_compressed(npz_path, **npz_values)
    wrong_outgoing = npz_values["solver_outgoing_amplitude"][index]
    json_rows[index]["solver_outgoing_amplitude"] = [wrong_outgoing.real, wrong_outgoing.imag]
    json_rows[index]["physical_boundary_outgoing_amplitude"] = [wrong_outgoing.real, wrong_outgoing.imag]
    json_rows[index]["outgoing_amplitude_at_boundary"] = [wrong_outgoing.real, wrong_outgoing.imag]
    json_path = tmp_path / "dtn_auxiliary_amplitudes_3d.json"
    json_path.write_text(json.dumps(json_rows), encoding="utf-8")
    csv_path = tmp_path / "dtn_port_diffraction_orders_3d.csv"
    with csv_path.open("r", newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        csv_fields = reader.fieldnames
        csv_rows = list(reader)
    wrong_text = f"{wrong_outgoing.real:.16e}{wrong_outgoing.imag:+.16e}j"
    csv_rows[index]["solver_outgoing_amplitude"] = wrong_text
    csv_rows[index]["physical_boundary_outgoing_amplitude"] = wrong_text
    csv_rows[index]["outgoing_amplitude_at_boundary"] = wrong_text
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=csv_fields)
        writer.writeheader()
        writer.writerows(csv_rows)
    bad = verify_v10_dtn_port_mode_table(
        csv_path,
        expected_channel_count=len(modes),
    )
    assert bad["passed"] is False
    assert "not total-minus-incident once" in bad["modal_amplitudes_npz"]["error"]
