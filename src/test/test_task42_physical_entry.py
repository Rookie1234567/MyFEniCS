"""Task42 A0 public input, material, geometry, and port-key contracts.

These tests exercise only input resolution, a tiny boundary-fitted mesh, and
analytic port-key enumeration.  They do not assemble a Maxwell operator, build
a QEP, or solve a PDE.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest
import ufl
from dolfinx import fem
from mpi4py import MPI

from scripts.run_case import main as run_case_main
from src.common.analytic_fields_3d import (
    electric_field_code_values,
    fresnel_reference,
    magnetic_field_code_values,
)
from src.geometry.mesh_builder_3d import (
    _stage4_axis_plan,
    build_airbox_mesh_3d,
)
from src.io import InputError, load_and_resolve
from src.io.input_validation import (
    TASK42_13P5_FULL3D_MODEL_ID,
    TASK42_SI_MATERIAL_RECORD_PATH,
    TASK42_SI_MATERIAL_RECORD_SHA256,
    simulation_config_3d_from_normalized,
    task42_external_mode_inventory_at_wavelength,
)
from src.postprocessing.diffraction_3d import _power_orders_for_reporting

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TASK42_INPUT = REPOSITORY_ROOT / (
    "input/official/task42hybrid_az90_50x50_17x20_0p7nm/"
    "13p5nm_p6h10_full3d_direct_mpi8.dat"
)
MATERIAL_RECORD = REPOSITORY_ROOT / TASK42_SI_MATERIAL_RECORD_PATH
OLD_TASK041_13P5_SI = (0.999002304859, 0.00182649365)


def _complex_vector(encoded: list[list[float]]) -> np.ndarray:
    return np.asarray(
        [complex(float(real), float(imag)) for real, imag in encoded],
        dtype=np.complex128,
    )


def _independent_air_orders(wavelength_nm: float) -> set[tuple[int, int]]:
    """Enumerate air orders directly from the 50 nm lattice and grazing angle."""

    period_nm = 50.0
    k0 = 2.0 * math.pi / wavelength_nm
    theta = math.radians(89.0)  # grazing angle 1 degree from the surface
    phi = math.radians(90.0)
    kx = k0 * math.sin(theta) * math.cos(phi)
    ky = k0 * math.sin(theta) * math.sin(phi)
    max_m = math.floor((k0 + abs(kx)) * period_nm / (2.0 * math.pi) + 1.0e-12)
    max_n = math.floor((k0 + abs(ky)) * period_nm / (2.0 * math.pi) + 1.0e-12)
    orders: set[tuple[int, int]] = set()
    for m in range(-max_m, max_m + 1):
        alpha = kx + 2.0 * math.pi * m / period_nm
        for n in range(-max_n, max_n + 1):
            gamma = ky + 2.0 * math.pi * n / period_nm
            dispersion = k0 * k0 - alpha * alpha - gamma * gamma
            if (m == 0 and n == 0) or dispersion > 1.0e-24:
                orders.add((m, n))
    return orders


def test_task42_public_validate_and_dry_run_bind_the_13p5_si_case(capsys):
    spec = load_and_resolve(TASK42_INPUT)
    assert spec.identity["model_id"] == TASK42_13P5_FULL3D_MODEL_ID
    assert spec.method["kind"] == "full3d_direct"
    assert spec.solver["linear_solver"] == "direct"
    assert spec.execution["mpi_size"] == 8
    assert spec.materials["substrate_name"] == "Si / silicon"
    assert spec.materials["grating_name"] == "Si / silicon"
    assert tuple(spec.materials["n_substrate"]) == (0.999001296237, 0.00182646094)
    assert tuple(spec.materials["n_grating"]) == (0.999001296237, 0.00182646094)
    provenance = spec.derived["material_provenance"]
    assert provenance["source"] == "user_supplied_delta_beta"
    assert provenance["material_record_sha256"] == TASK42_SI_MATERIAL_RECORD_SHA256
    assert provenance["experimental_qualification"] == "not_claimed"

    assert run_case_main([str(TASK42_INPUT), "--validate-only"]) == 0
    validate_payload = json.loads(capsys.readouterr().out)
    assert validate_payload == {
        "method": "full3d_direct",
        "model_id": TASK42_13P5_FULL3D_MODEL_ID,
        "run_id": "task42_13p5_p6h10_full3d_direct_mpi8",
        "status": "valid",
    }

    assert run_case_main([str(TASK42_INPUT), "--dry-run"]) == 0
    dry_run = json.loads(capsys.readouterr().out)
    assert dry_run["method"] == "full3d_direct"
    assert dry_run["mpi_size"] == 8
    assert dry_run["grazing_angle_deg"] == 1.0
    assert dry_run["azimuth_deg"] == 90.0
    assert dry_run["external_mode_inventory"]["source"] == "outgoing_port_modes_3d"
    assert dry_run["external_mode_inventory"]["counts"]["unique_spatial_mn_per_side"]["top"] == 42
    assert dry_run["resolved_method_adapter"]["status"] == "connected"
    assert spec.output["diffraction_order_max_m"] == 3
    assert spec.output["diffraction_order_max_n"] == 7
    all_external_keys = dry_run["external_mode_inventory"]["keys"]
    assert {str(key["side"]) for key in all_external_keys} == {"top", "bottom"}
    assert all(
        abs(int(key["m"])) <= spec.output["diffraction_order_max_m"]
        and abs(int(key["n"])) <= spec.output["diffraction_order_max_n"]
        for key in all_external_keys
    )
    reporting_orders = _power_orders_for_reporting(
        simulation_config_3d_from_normalized(spec.as_jsonable())
    )
    reporting_mn = {(int(order.m), int(order.n)) for order in reporting_orders}
    legal_external_mn = {
        (int(key["m"]), int(key["n"])) for key in all_external_keys
    }
    assert max(abs(m) for m, _ in legal_external_mn) == 3
    assert max(abs(n) for _, n in legal_external_mn) == 7
    assert legal_external_mn <= reporting_mn

    wavevector = _complex_vector(dry_run["wavevector"])
    polarization = _complex_vector(dry_run["polarization"])
    k0 = 2.0 * math.pi / 13.5
    np.testing.assert_allclose(
        wavevector,
        np.asarray(
            (
                k0 * math.sin(math.radians(89.0)) * math.cos(math.radians(90.0)),
                k0 * math.sin(math.radians(89.0)) * math.sin(math.radians(90.0)),
                -k0 * math.cos(math.radians(89.0)),
            ),
            dtype=np.complex128,
        ),
        rtol=0.0,
        atol=2.0e-15,
    )
    np.testing.assert_allclose(
        polarization,
        np.asarray((-1.0, 0.0, 0.0), dtype=np.complex128),
        rtol=0.0,
        atol=2.0e-15,
    )
    np.testing.assert_allclose(
        dry_run["floquet_phases"]["x"], [1.0, 0.0], atol=1.0e-14
    )
    ky = k0 * math.sin(math.radians(89.0))
    phase_y = ky * 50.0
    np.testing.assert_allclose(
        dry_run["floquet_phases"]["y"],
        [math.cos(phase_y), math.sin(phase_y)],
        rtol=0.0,
        atol=2.0e-14,
    )

    cfg = simulation_config_3d_from_normalized(spec.as_jsonable())
    coordinates = np.asarray(((4.0, 7.0, 125.0),), dtype=np.float64)
    electric = electric_field_code_values(cfg, coordinates)[0]
    magnetic = magnetic_field_code_values(cfg, coordinates)[0]
    k_incident = np.asarray(cfg.wavevector, dtype=np.complex128)
    k_reflected = k_incident.copy()
    k_reflected[2] *= -1.0
    phase_incident = np.exp(1j * np.dot(k_incident, coordinates[0]))
    phase_reflected = np.exp(1j * np.dot(k_reflected, coordinates[0]))
    s_vector = np.asarray(cfg.polarization_vector, dtype=np.complex128)
    reflection = complex(fresnel_reference(cfg)["r_s"])
    expected_electric = cfg.incident_amplitude * s_vector * (
        phase_incident + reflection * phase_reflected
    )
    expected_magnetic = cfg.incident_amplitude * (
        np.cross(k_incident, s_vector) * phase_incident
        + reflection * np.cross(k_reflected, s_vector) * phase_reflected
    ) / (cfg.k0 * cfg.mu_r)
    np.testing.assert_allclose(electric, expected_electric, rtol=1.0e-13, atol=1.0e-14)
    np.testing.assert_allclose(magnetic, expected_magnetic, rtol=1.0e-13, atol=1.0e-14)
    assert abs(np.dot(k_incident, s_vector)) <= 1.0e-12
    poynting = 0.5 * np.real(np.cross(electric, np.conjugate(magnetic)))
    expected_poynting = 0.5 * np.real(
        np.cross(expected_electric, np.conjugate(expected_magnetic))
    )
    np.testing.assert_allclose(poynting, expected_poynting, rtol=5.0e-13, atol=2.0e-14)
    assert poynting[2] < 0.0


def test_task42_material_record_has_the_frozen_user_messages_and_hash():
    raw = MATERIAL_RECORD.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == TASK42_SI_MATERIAL_RECORD_SHA256
    record = json.loads(raw)
    assert record["materials"]["substrate"] == "Si / silicon"
    assert record["materials"]["grating"] == "Si / silicon"
    quoted_values = record["user_overrides"][0]["quoted_values"]
    assert quoted_values == {
        "lambda_13p5_nm_Delta": "0.000998703763",
        "lambda_13p5_nm_Beta": "0.00182646094",
        "lambda_0p7_nm_Delta": "0.000196346038",
        "lambda_0p7_nm_Beta": "8.98053258E-06",
    }
    assert record["materials"]["wavelengths"]["13.5nm"]["provenance"] == "user_supplied_delta_beta"
    assert record["materials"]["wavelengths"]["0.7nm"]["provenance"] == "user_supplied_delta_beta"
    assert record["materials"]["wavelengths"]["0.7nm"]["use_status"] == (
        "frozen_material_input; no_0p7nm_PDE_authorized_or_run_in_A0"
    )


@pytest.mark.parametrize(
    ("old", "new", "error_path"),
    (
        ('azimuth_deg = 90.0', 'azimuth_deg = 0.0', "incidence.azimuth_deg"),
        ('grating_width_y_nm = 20.0', 'grating_width_y_nm = 50.0', "grating_width_y_nm"),
        (
            'n_substrate = [0.999001296237, 0.00182646094]',
            f'n_substrate = [{OLD_TASK041_13P5_SI[0]}, {OLD_TASK041_13P5_SI[1]}]',
            "materials.n_substrate",
        ),
    ),
)
def test_task42_rejects_wrong_azimuth_geometry_or_old_task041_si(
    tmp_path: Path, old: str, new: str, error_path: str
):
    source = TASK42_INPUT.read_text(encoding="utf-8")
    assert source.count(old) == 1
    path = tmp_path / "invalid_task42_case.dat"
    path.write_text(source.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(InputError, match=error_path):
        load_and_resolve(path)


def test_task42_rejects_old_task041_packet_route_before_worker(tmp_path, capsys):
    old_packet = tmp_path / "task041-packet"
    result = run_case_main(
        [str(TASK42_INPUT), "--producer-packet-root", str(old_packet)]
    )
    captured = capsys.readouterr()
    assert result == 2
    assert "--producer-packet-root is supported only for Task041 BAL_H profiles" in captured.err
    assert not old_packet.exists()


def test_task42_builds_the_boundary_fitted_material_mesh_with_expected_volumes(
    tmp_path: Path,
):
    spec = load_and_resolve(TASK42_INPUT)
    cfg = simulation_config_3d_from_normalized(spec.as_jsonable())
    plan = _stage4_axis_plan(cfg, MPI.COMM_WORLD.size)
    assert plan.mesh_spacing_mode_resolved == "boundary_fitted"
    assert plan.material_plane_alignment["all_aligned"] is True
    for value in (-10.0, 0.0, 10.0, 110.0, 120.0, 130.0):
        assert np.any(np.isclose(plan.z_values, value, atol=1.0e-12, rtol=0.0))
    for value in (16.5, 33.5):
        assert np.any(np.isclose(plan.x_values, value, atol=1.0e-12, rtol=0.0))
    for value in (15.0, 35.0):
        assert np.any(np.isclose(plan.y_values, value, atol=1.0e-12, rtol=0.0))

    mesh_data = build_airbox_mesh_3d(cfg, tmp_path / "task42-a0-mesh")
    dx = ufl.Measure("dx", domain=mesh_data.mesh, subdomain_data=mesh_data.cell_tags)
    expected = {
        cfg.tags.air: 284200.0,
        cfg.tags.substrate: 25000.0,
        cfg.tags.grating: 40800.0,
    }
    for tag, expected_volume in expected.items():
        local_volume = fem.assemble_scalar(fem.form(1.0 * dx(tag)))
        total_volume = MPI.COMM_WORLD.allreduce(local_volume, op=MPI.SUM)
        assert total_volume == pytest.approx(expected_volume, rel=0.0, abs=1.0e-8)


@pytest.mark.parametrize(
    ("wavelength_nm", "expected_spatial_count"),
    ((13.5, 42), (0.7, 16031)),
)
def test_task42_air_order_inventory_matches_independent_lattice_and_actual_keys(
    wavelength_nm: float, expected_spatial_count: int
):
    spec = load_and_resolve(TASK42_INPUT)
    config = spec.as_jsonable()
    planned = task42_external_mode_inventory_at_wavelength(config, wavelength_nm)
    expected_orders = _independent_air_orders(wavelength_nm)
    inventory = planned["external_mode_inventory"]
    actual_modes = inventory["modes"]
    actual_top_orders = {
        (int(mode["m"]), int(mode["n"]))
        for mode in actual_modes
        if mode["side"] == "top"
    }
    actual_top_keys = {
        (str(mode["side"]), int(mode["m"]), int(mode["n"]), str(mode["polarization"]))
        for mode in actual_modes
        if mode["side"] == "top"
    }
    expected_top_keys = {
        ("top", m, n, polarization)
        for m, n in expected_orders
        for polarization in ("s", "p")
    }
    planned_top_keys = {
        (row["side"], row["m"], row["n"], row["polarization"])
        for row in inventory["keys"]
        if row["side"] == "top"
    }
    assert len(expected_orders) == expected_spatial_count
    assert actual_top_orders == expected_orders
    assert actual_top_keys == expected_top_keys
    assert planned_top_keys == expected_top_keys
    assert inventory["count"] == len(inventory["keys"]) == len(inventory["modes"])
    assert {
        (row["side"], row["m"], row["n"], row["polarization"])
        for row in inventory["modes"]
    } == {
        (row["side"], row["m"], row["n"], row["polarization"])
        for row in inventory["keys"]
    }
    assert inventory["count"] > planned["air_side_external_key_count"]
    assert planned["air_side_spatial_order_count"] == expected_spatial_count
    assert planned["air_side_external_key_count"] == 2 * expected_spatial_count
    assert planned["packet_material_binding"]["packet_generated"] is False
    assert planned["packet_material_binding"]["mesh_or_qep_generated"] is False
    assert planned["pde_status"] == "not_run"
    assert planned["material_identity"]["source"] == "user_supplied_delta_beta"
    assert planned["material_identity"]["material_record_sha256"] == (
        TASK42_SI_MATERIAL_RECORD_SHA256
    )
    assert spec.incidence["azimuth_deg"] == 90.0
