from pathlib import Path

import pytest
import numpy as np

from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.input_validation import (
    simulation_config_2d_from_normalized,
    simulation_config_3d_from_normalized,
    task039_incidence_identity,
    task039_v3_2d_auto_dtn_order_count,
)
from src.common.modes_3d import incident_power_3d
from src.postprocessing.power_metrics import _is_propagating
from src.solvers.solve_te_maxwell import _positive_sqrt


ROOT = Path(__file__).resolve().parents[2]
V3_2D = ROOT / "input/official/task039"
V3_CASES = (
    ("5nm_1deg_2d_te_p6h5_direct_mpi1.dat", 5.0),
    ("5nm_1deg_2d_te_p6h4_direct_mpi1.dat", 4.0),
    ("5nm_1deg_2d_te_p6h3_direct_mpi1.dat", 3.0),
    ("5nm_1deg_2d_te_p6h2_direct_mpi1.dat", 2.0),
    ("5nm_1deg_2d_te_p6h1p5_direct_mpi1.dat", 1.5),
)


@pytest.mark.parametrize(("filename", "mesh_target"), V3_CASES)
def test_v3_1deg_te_inputs_resolve_with_shared_identity(filename, mesh_target):
    specification = load_and_resolve(V3_2D / filename)
    assert specification.identity["dimension"] == 2
    assert specification.method["kind"] == "2d_port"
    assert specification.method["constraint_backend"] == "manual"
    assert specification.boundary["vertical_boundary"] == "dtn"
    assert specification.boundary["use_pml"] is False
    assert specification.boundary["dtn_order_policy"] == "auto_propagating"
    assert specification.boundary["dtn_assembly"] == "explicit"
    assert specification.incidence["grazing_angle_deg"] == 1.0
    assert "tilt_from_downward_y_deg" not in specification.incidence
    assert specification.discretization["mesh_target_nm"] == mesh_target
    assert specification.derived["internal"]["incident_theta_deg"] == 89.0
    assert specification.derived["port_dtn_order_count"] == 21
    identity = specification.derived["angle_identity"]
    assert identity["grazing_angle_deg"] == 1.0
    assert identity["theta_from_downward_axis_deg"] == 89.0
    assert identity["direction_2d_xz"] == pytest.approx(
        identity["direction_3d_xyz"][::2], abs=1.0e-15
    )
    assert identity["field_component_identity"] == "2d_TE_scalar_to_3d_S_Ey"
    assert identity["magnetic_field_mapping"]["H3D_x"] == "-H2D_x_scaled/k0"
    assert identity["magnetic_field_mapping"]["H3D_z"] == "-H2D_y_scaled/k0"
    assert (
        "P2D_weighted=P3D_weighted*k0/period_y_nm" in identity["incident_power_mapping"]
    )
    assert specification.derived["material_provenance"]["wavelength_nm"] == 5.0


def test_v3_angle_identity_matches_3d_s_direction():
    identity = task039_incidence_identity(
        {
            "dimension": 3,
            "incidence": {"grazing_angle_deg": 1.0, "azimuth_deg": 0.0},
        }
    )
    assert identity["direction_3d_xyz"] == pytest.approx(
        [0.9998476951563913, 0.0, -0.0174524064372836], abs=1.0e-15
    )


def test_v3_auto_dtn_bound_contains_both_media():
    specification = load_and_resolve(V3_2D / "5nm_1deg_2d_te_p6h5_direct_mpi1.dat")
    payload = specification.as_jsonable()
    order_count = task039_v3_2d_auto_dtn_order_count(payload)
    assert order_count == 21
    assert specification.derived["port_dtn_order_count"] == order_count
    cfg = simulation_config_2d_from_normalized(payload)
    assert cfg.port_use_diffraction_orders is True
    identity = specification.derived["angle_identity"]
    assert cfg.kx / cfg.k0 == pytest.approx(identity["direction_2d_xz"][0], abs=1.0e-12)
    assert cfg.ky / cfg.k0 == pytest.approx(identity["direction_2d_xz"][1], abs=1.0e-12)

    candidate_orders = range(-order_count - 5, order_count + 6)
    propagating = {"top": set(), "bottom": set()}
    for order in candidate_orders:
        alpha = cfg.kx + 2.0 * np.pi * order / cfg.period_x
        for side, index in (("top", cfg.n_air), ("bottom", cfg.n_substrate)):
            beta = _positive_sqrt((cfg.k0 * index) ** 2 - alpha**2)
            if _is_propagating(beta):
                propagating[side].add(order)
    retained = set(range(-order_count, order_count + 1))
    assert propagating["top"] == set(range(-19, 1))
    assert propagating["bottom"] == set(range(-19, 0))
    assert propagating["top"] <= retained
    assert propagating["bottom"] <= retained
    assert order_count != payload["output"]["diffraction_order_max_m"]
    payload["output"]["diffraction_order_max_m"] = 0
    assert task039_v3_2d_auto_dtn_order_count(payload) == order_count


def test_ordinary_2d_downward_tilt_path_is_unchanged():
    specification = load_and_resolve(ROOT / "input/templates/ordinary_2d_example.dat")
    assert specification.incidence["tilt_from_downward_y_deg"] == 0.0
    assert "grazing_angle_deg" not in specification.incidence
    assert specification.derived["internal"]["incident_theta_deg"] == 0.0
    assert "angle_identity" not in specification.derived


def test_ordinary_3d_resolved_payload_has_no_task039_angle_identity():
    specification = load_and_resolve(
        ROOT / "input/official/task039/5nm_p6h5_full3d_direct_mpi8.dat"
    )
    assert "angle_identity" not in specification.derived
    non_task = load_and_resolve(ROOT / "input/smoke/3d_stage4a_flat_layer_direct.dat")
    assert "angle_identity" not in non_task.derived


def test_v3_3d_model_id_boundary_and_identity_fixture(tmp_path):
    source = (
        ROOT / "input/official/task039/5nm_p6h5_full3d_direct_mpi8.dat"
    ).read_text()
    accepted = tmp_path / "v3_3d.dat"
    accepted.write_text(
        source.replace(
            'model_id = "task039_5nm_full3d_direct"',
            'model_id = "task039_5nm_v3_1deg_s5_full3d"',
            1,
        ).replace("grazing_angle_deg = 10.0", "grazing_angle_deg = 1.0", 1)
    )
    specification = load_and_resolve(accepted)
    assert specification.derived["angle_identity"]["field_component_identity"] == (
        "2d_TE_scalar_to_3d_S_Ey"
    )
    assert specification.derived["angle_identity"]["direction_3d_xyz"] == pytest.approx(
        [0.9998476951563913, 0.0, -0.0174524064372836], abs=1.0e-15
    )
    cfg2 = simulation_config_2d_from_normalized(
        load_and_resolve(V3_2D / "5nm_1deg_2d_te_p6h5_direct_mpi1.dat").as_jsonable()
    )
    cfg3 = simulation_config_3d_from_normalized(specification.as_jsonable())

    def assert_relative(left, right):
        scale = max(abs(complex(left)), abs(complex(right)), 1.0e-30)
        assert abs(complex(left) - complex(right)) / scale <= 1.0e-12

    assert_relative(cfg2.kx, cfg3.kx)
    assert_relative(cfg2.ky, cfg3.kz)
    np.testing.assert_allclose(
        cfg3.s_polarization_vector,
        np.asarray([0.0, 1.0, 0.0], dtype=np.complex128),
        rtol=0.0,
        atol=1.0e-12,
    )
    h2_scaled = np.asarray([cfg2.ky, -cfg2.kx], dtype=np.complex128)
    h3 = (
        np.cross(
            np.asarray(cfg3.wavevector, dtype=np.complex128),
            np.asarray([0.0, 1.0, 0.0], dtype=np.complex128),
        )
        / cfg3.k0
    )
    np.testing.assert_allclose(
        h3[[0, 2]], -h2_scaled / cfg2.k0, rtol=1.0e-12, atol=1.0e-13
    )
    beta = _positive_sqrt((cfg2.k0 * cfg2.n_air) ** 2 - cfg2.kx**2)
    direction_2d = np.asarray([cfg2.kx, beta], dtype=np.complex128)
    direction_3d = np.asarray([cfg3.kx, 0.0, beta], dtype=np.complex128)
    np.testing.assert_allclose(
        direction_2d / np.linalg.norm(direction_2d),
        direction_3d[[0, 2]] / np.linalg.norm(direction_3d),
        rtol=1.0e-12,
        atol=1.0e-13,
    )
    p2d = 0.5 * float(np.real(beta)) * cfg2.period_x
    p3d = incident_power_3d(cfg3)
    assert_relative(p2d, p3d * cfg2.k0 / cfg3.period_y)

    for mesh_target in ("4.5", "4.0"):
        refined = tmp_path / f"v3_3d_h{mesh_target}.dat"
        refined.write_text(
            accepted.read_text().replace(
                "mesh_target_nm = 5.0", f"mesh_target_nm = {mesh_target}", 1
            )
        )
        assert (
            load_and_resolve(refined).derived["angle_identity"]["grazing_angle_deg"]
            == 1.0
        )

    rejected = tmp_path / "v3_3d_rejected.dat"
    rejected.write_text(
        accepted.read_text().replace(
            "task039_5nm_v3_1deg_s5_full3d",
            "task039_5nm_v3_1deg_s5_full3d_other",
            1,
        )
    )
    with pytest.raises(InputError):
        load_and_resolve(rejected)


def test_v3_rejects_both_angle_fields(tmp_path):
    source = (V3_2D / "5nm_1deg_2d_te_p6h5_direct_mpi1.dat").read_text()
    path = tmp_path / "ambiguous_angle.dat"
    path.write_text(
        source.replace(
            "grazing_angle_deg = 1.0",
            "grazing_angle_deg = 1.0\ntilt_from_downward_y_deg = 89.0",
            1,
        )
    )
    with pytest.raises(InputError, match="exactly one"):
        load_and_resolve(path)


@pytest.mark.parametrize(
    "replacement",
    [
        ("grazing_angle_deg = 1.0", "grazing_angle_deg = 2.0"),
        ('polarization = "te"', 'polarization = "tm"'),
        ("mesh_target_nm = 5.0", "mesh_target_nm = 1.0"),
    ],
)
def test_v3_profile_rejects_physical_or_mesh_near_miss(tmp_path, replacement):
    source = (V3_2D / "5nm_1deg_2d_te_p6h5_direct_mpi1.dat").read_text()
    old, new = replacement
    path = tmp_path / "near_miss.dat"
    path.write_text(source.replace(old, new, 1))
    with pytest.raises(InputError):
        load_and_resolve(path)


def test_v3_profile_requires_shared_grazing_field(tmp_path):
    source = (V3_2D / "5nm_1deg_2d_te_p6h5_direct_mpi1.dat").read_text()
    path = tmp_path / "tilt_override.dat"
    path.write_text(
        source.replace("grazing_angle_deg = 1.0", "tilt_from_downward_y_deg = 89.0")
    )
    with pytest.raises(InputError, match="grazing_angle_deg"):
        load_and_resolve(path)
