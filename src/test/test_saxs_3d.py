from __future__ import annotations

import csv

import numpy as np
import pytest

from src.postprocessing.saxs_3d import (
    EXTRA_2D_FEM_ORDERS,
    PRIMARY_FEM_ORDERS,
    _detector_projection,
    postprocess_to_saxs,
    write_saxs_result,
)


WAVELENGTH_NM = 0.7135227949132827
PERIOD_NM = (50.0, 50.0)
BEAM = (0.9, 0.0)


def _complex_json(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def _run(pose_deg: float, *, run_id: str) -> dict:
    alpha_i = np.deg2rad(BEAM[0])
    phi = np.deg2rad(90.0 - pose_deg - BEAM[1])
    kin = np.asarray(
        (np.cos(alpha_i) * np.cos(phi), np.cos(alpha_i) * np.sin(phi)),
        dtype=np.float64,
    )
    k0 = 2.0 * np.pi / WAVELENGTH_NM
    orders = []
    all_orders = list(PRIMARY_FEM_ORDERS) + list(EXTRA_2D_FEM_ORDERS)
    for index, (m, n) in enumerate(all_orders):
        kout_xy = kin + np.asarray((m * WAVELENGTH_NM / PERIOD_NM[0], n * WAVELENGTH_NM / PERIOD_NM[1]))
        kz_unit = np.sqrt(1.0 - float(np.dot(kout_xy, kout_xy)))
        assert kz_unit > 0.0
        wavevector = (
            k0 * kout_xy[0],
            k0 * kout_xy[1],
            k0 * kz_unit,
        )
        for polarization, power, amplitude in (
            ("s", 0.04 + 0.01 * index, 0.3 + 0.02j * index),
            ("p", 0.01 + 0.002 * index, 0.1 - 0.01j * index),
        ):
            orders.append(
                {
                    "side": "top",
                    "m": m,
                    "n": n,
                    "polarization": polarization,
                    "alpha": _complex_json(complex(wavevector[0])),
                    "gamma": _complex_json(complex(wavevector[1])),
                    "kz": _complex_json(complex(wavevector[2])),
                    "outgoing_amplitude": _complex_json(complex(amplitude)),
                    "outgoing_amplitude_at_boundary": _complex_json(complex(amplitude)),
                    "boundary_phase": _complex_json(0.8 + 0.1j * (index + 1)),
                    "R": power,
                    "propagating": True,
                    "power_carrying": True,
                }
            )
    return {
        "orders": orders,
        "port_metrics": {"dtn_port_top_reference_z": 130.0},
        "provenance": {"kind": "synthetic_test_fixture"},
        "run_manifest": {"run_id": run_id},
        "resolved_config": {
            "incidence": {
                "wavelength_nm": WAVELENGTH_NM,
                "grazing_angle_deg": BEAM[0],
                "azimuth_deg": 90.0 - pose_deg,
                "electric_amplitude": [1.0, 0.0],
            },
            "geometry": {"period_x_nm": PERIOD_NM[0], "period_y_nm": PERIOD_NM[1]},
        },
    }


def _acquisition(**overrides) -> dict:
    acquisition = {
        "fem_orders": PRIMARY_FEM_ORDERS,
        "pose_deg": 6.0,
        "beam_distribution_deg": (BEAM,),
        "beam_weights": (1.0,),
        "wavelength_nm": WAVELENGTH_NM,
        "cell_period_nm": PERIOD_NM,
        "period_number": (0, 0),
    }
    acquisition.update(overrides)
    return acquisition


def test_primary_tensor_formula_shapes_and_separate_extra_normalization():
    run = _run(6.0, run_id="pose-6")
    result = postprocess_to_saxs(run, _acquisition())
    assert result["intensity"].shape == (1, 1, 5, 1)
    assert result["intensity_raw"].shape == (1, 1, 5, 1)
    assert result["active_angle"].shape == (2, 5, 1)
    assert result["integrated_intensity"].shape == (1, 1, 5)
    assert result["extra_orders"]["fem_orders"].shape == (3, 2)
    assert result["extra_orders"]["intensity"].shape == (1, 1, 3, 1)

    alpha_i = np.deg2rad(BEAM[0])
    alpha_f = result["active_angle"][0, :, 0]
    k0 = 2.0 * np.pi / WAVELENGTH_NM
    expected_raw = (
        result["R_total"][:, 0]
        * np.prod(PERIOD_NM) ** 2
        * np.sin(alpha_i)
        * np.sin(alpha_f)
        / k0**2
    )
    np.testing.assert_allclose(result["intensity_raw"][0, 0, :, 0], expected_raw)
    np.testing.assert_allclose(result["intensity"][0, 0, :, 0], expected_raw / expected_raw.mean())

    with_extras = postprocess_to_saxs(
        run,
        _acquisition(extra_fem_orders=EXTRA_2D_FEM_ORDERS),
    )
    np.testing.assert_array_equal(with_extras["intensity_raw"], result["intensity_raw"])
    assert with_extras["extra_orders"]["fem_orders"].shape == (3, 2)
    assert with_extras["extra_orders"]["intensity"].shape == (1, 1, 3, 1)


def test_multiple_poses_require_an_explicit_independent_run_per_pose():
    orders = np.tile(np.asarray(PRIMARY_FEM_ORDERS), (2, 1))
    poses = np.repeat((6.0, 7.0), 5)
    run_6 = _run(6.0, run_id="pose-6")
    run_7 = _run(7.0, run_id="pose-7")
    run_map = [[run_6] for _ in range(5)] + [[run_7] for _ in range(5)]
    result = postprocess_to_saxs(
        {"runs_by_channel_ray": run_map},
        _acquisition(fem_orders=orders, pose_deg=poses, extra_fem_orders=[]),
    )
    assert result["intensity"].shape == (1, 1, 10, 1)
    assert result["model_to_saxs_matrix"].shape == (10, 3, 3)
    assert result["metadata"]["source_runs"][0] == ["pose-6"]
    assert result["metadata"]["source_runs"][5] == ["pose-7"]

    with pytest.raises(ValueError, match="multiple sample poses"):
        postprocess_to_saxs(run_6, _acquisition(fem_orders=orders, pose_deg=poses))


def test_a_saved_run_cannot_be_reused_for_a_second_ray_or_missing_positive_ray():
    run = _run(6.0, run_id="pose-6")
    acquisition = _acquisition(
        beam_distribution_deg=((0.9, 0.0), (0.9, 0.0)),
        beam_weights=(0.5, 0.5),
    )
    with pytest.raises(ValueError, match="cannot be reused"):
        postprocess_to_saxs({"runs": [run, run]}, acquisition)

    with pytest.raises(ValueError, match="Missing positive-weight"):
        postprocess_to_saxs(
            {"runs_by_channel_ray": [[None] for _ in range(5)]},
            _acquisition(),
        )


def test_failed_production_run_summary_is_rejected():
    run = _run(6.0, run_id="failed-run")
    run.pop("provenance")
    run["run_summary"] = {
        "status": "failed",
        "exit_status": 1,
        "result_classification": "worker_exit1",
    }
    run["run_manifest"].update(
        status="finished", exit_status=1, execution_mode="full_solve"
    )
    run["solver_summary"] = {"passed": True, "complete_solve": True, "errors": []}
    with pytest.raises(ValueError, match="completed full-solve"):
        postprocess_to_saxs(run, _acquisition(extra_fem_orders=[]))


def test_detector_accumulates_received_points_and_leaves_outside_orders_unreceived():
    result = {
        "k_out_saxs_over_k0": np.asarray(
            [[[1.0, 0.0, 0.0]], [[1.0, 0.0, 0.0]], [[1.0, 2.0, 0.0]]]
        ),
        "propagating": np.ones((3, 1), dtype=bool),
        "calculated_mask": np.ones((3, 1), dtype=bool),
        "intensity": np.asarray([[[[1.0], [2.0], [4.0]]]]),
    }
    detector = _detector_projection(
        result,
        {
            "distance_m": 0.2,
            "shape": (2, 2),
            "pixel_size_m": 0.1,
            "first_center_yz_m": (-0.05, -0.05),
        },
    )
    assert detector["in_detector"][:, 0].tolist() == [True, True, False]
    assert detector["detector_pixel_rc"][2, 0].tolist() == [-1, -1]
    assert detector["detector_image"].sum() == 3.0
    assert detector["detected_order_intensity"].tolist() == [1.0, 2.0, 0.0]


def test_csv_retains_phase_origin_port_and_boundary_amplitudes(tmp_path):
    result = postprocess_to_saxs(
        _run(6.0, run_id="csv-phase"),
        _acquisition(extra_fem_orders=[], phase_reference_z_nm=120.0),
    )
    paths = write_saxs_result(result, tmp_path)
    with open(paths["csv"], newline="", encoding="utf-8") as stream:
        row = next(csv.DictReader(stream))

    assert float(row["origin_amplitude_s_re"]) == pytest.approx(0.3)
    assert float(row["port_amplitude_s_re"]) == pytest.approx(0.3)
    assert row["boundary_phase_s_present"] == "True"
    assert float(row["boundary_phase_s_re"]) == pytest.approx(0.8)
    assert float(row["phase_reference_plane_z_nm"]) == 120.0
    assert float(row["port_reference_plane_z_nm"]) == 130.0
