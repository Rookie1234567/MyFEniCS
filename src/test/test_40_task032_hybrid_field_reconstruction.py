from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import numpy as np
from mpi4py import MPI

from src.postprocessing.hybrid_field_reconstruction import (
    ModalFieldReconstructor,
    ModalPlaneSamples,
    compare_selected_planes_to_reference,
    element_safe_middle_offsets,
    relative_sample_error,
    sampled_plane_flux_and_vacuum_energy,
)
from src.common.units import VACUUM_C, VACUUM_ETA0


class TestTask032HybridFieldReconstruction(unittest.TestCase):
    def test_relative_sample_error_is_scale_symmetric(self) -> None:
        first = np.asarray([[1.0 + 1.0j, 2.0], [0.5j, -3.0]], dtype=np.complex128)
        second = 1.01 * first
        forward = relative_sample_error(first, second)
        backward = relative_sample_error(second, first)
        self.assertAlmostEqual(
            forward["relative_l2"], backward["relative_l2"], places=15
        )
        self.assertGreater(forward["max_pointwise_absolute"], 0.0)

    def test_two_sided_coefficients_use_only_decaying_directions(self) -> None:
        reconstructor = ModalFieldReconstructor.__new__(ModalFieldReconstructor)
        reconstructor.positive = SimpleNamespace(
            modes=[SimpleNamespace(beta=1.2 + 0.3j), SimpleNamespace(beta=0.7 + 0.1j)]
        )
        reconstructor.negative = SimpleNamespace(
            modes=[SimpleNamespace(beta=-1.2 - 0.3j), SimpleNamespace(beta=-0.7 - 0.1j)]
        )
        reconstructor.bottom_z_nm = 10.0
        reconstructor.top_z_nm = 110.0
        amplitudes = np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.complex128)
        middle = reconstructor.coefficients_at_z(amplitudes, 60.0)
        self.assertTrue(np.all(np.abs(middle[:2]) < np.abs(amplitudes[:2])))
        self.assertTrue(np.all(np.abs(middle[2:]) < np.abs(amplitudes[2:])))
        self.assertTrue(np.all(np.isfinite(middle)))

    def test_curl_e_opt_in_uses_propagation_beta_not_traction_beta(self) -> None:
        reconstructor = ModalFieldReconstructor.__new__(ModalFieldReconstructor)
        reconstructor.cfg = SimpleNamespace(electric_field_scale_V_per_m=1.0)
        reconstructor.positive = SimpleNamespace(modes=[object()])
        reconstructor.negative = SimpleNamespace(modes=[object()])
        reconstructor._modes = (
            *reconstructor.positive.modes,
            *reconstructor.negative.modes,
        )
        reconstructor.bottom_z_nm = 10.0
        reconstructor.top_z_nm = 110.0
        reconstructor._positive_propagation_beta = np.asarray([0.2 + 0.0j])
        reconstructor._negative_propagation_beta = np.asarray([-0.3 + 0.0j])
        reconstructor._positive_traction_beta = np.asarray([7.0 + 0.0j])
        reconstructor._negative_traction_beta = np.asarray([-8.0 + 0.0j])

        def sample(_points, *, magnetic_betas=None):
            betas = (
                reconstructor._magnetic_traction_betas()
                if magnetic_betas is None
                else np.asarray(magnetic_betas)
            )
            electric = np.ones((2, 1, 3), dtype=np.complex128)
            magnetic = np.zeros((2, 1, 3), dtype=np.complex128)
            magnetic[:, :, 0] = betas[:, None]
            return electric, magnetic

        reconstructor._sample_mode_bases = sample
        native = reconstructor.selected_planes([1.0, 1.0], [0.0], [0.0], [60.0])
        curl_e = reconstructor.selected_planes_from_curl_e(
            [1.0, 1.0], [0.0], [0.0], [60.0]
        )
        self.assertFalse(np.allclose(native.magnetic_A_per_m, curl_e.magnetic_A_per_m))
        reconstructor._positive_traction_beta = (
            reconstructor._positive_propagation_beta.copy()
        )
        reconstructor._negative_traction_beta = (
            reconstructor._negative_propagation_beta.copy()
        )
        native_equal = reconstructor.selected_planes([1.0, 1.0], [0.0], [0.0], [60.0])
        curl_equal = reconstructor.selected_planes_from_curl_e(
            [1.0, 1.0], [0.0], [0.0], [60.0]
        )
        np.testing.assert_allclose(
            native_equal.magnetic_A_per_m, curl_equal.magnetic_A_per_m
        )

    def test_element_safe_offsets_use_real_axis_cell_midpoints(self) -> None:
        axis_plan = SimpleNamespace(
            z_values=np.asarray([0.0, 10.0, 20.0, 40.0, 70.0, 100.0, 110.0, 120.0])
        )
        bottom, top = element_safe_middle_offsets(axis_plan)
        self.assertEqual(bottom["role"], "bottom_element_safe_offset")
        self.assertEqual(top["role"], "top_element_safe_offset")
        self.assertEqual((bottom["element_id"], top["element_id"]), (1, 5))
        self.assertEqual((bottom["slab_index"], top["slab_index"]), (1, 5))
        self.assertEqual((bottom["z_nm"], top["z_nm"]), (15.0, 105.0))
        self.assertTrue(10.0 < bottom["z_nm"] < 110.0)
        self.assertTrue(10.0 < top["z_nm"] < 110.0)
        self.assertEqual(bottom["source"], "mesh_element_interior_midpoint")
        self.assertEqual(top["source"], "mesh_element_interior_midpoint")
        self.assertIn("distance_from_interface_nm", bottom)
        self.assertIn("distance_from_interface_nm", top)
        with self.assertRaises(ValueError):
            element_safe_middle_offsets(
                SimpleNamespace(z_values=np.asarray([0.0, 12.0, 40.0, 110.0, 120.0]))
            )

    def test_sampled_flux_and_energy_use_physical_field_values(self) -> None:
        electric = np.asarray([[[[2.0, 0.0, 0.0]]]], dtype=np.complex128)
        magnetic = np.asarray([[[[0.0, 3.0, 0.0]]]], dtype=np.complex128)
        flux, energy = sampled_plane_flux_and_vacuum_energy(electric, magnetic)
        self.assertEqual(flux.tolist(), [3.0])
        epsilon_0 = 1.0 / (VACUUM_C * VACUUM_ETA0)
        mu_0 = VACUUM_ETA0 / VACUUM_C
        self.assertAlmostEqual(energy[0], 0.25 * (4.0 * epsilon_0 + 9.0 * mu_0))

    def test_selected_plane_reference_comparison_round_trip(self) -> None:
        x = np.asarray([0.25, 0.75])
        y = np.asarray([0.5])
        z = np.asarray([10.0, 30.0, 110.0])
        electric = (
            np.arange(18, dtype=np.float64).reshape((3, 1, 2, 3)).astype(np.complex128)
        )
        magnetic = (0.1j * electric).astype(np.complex128)
        samples = ModalPlaneSamples(x, y, z, electric, magnetic)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference.npz"
            np.savez_compressed(
                path,
                x_nm=x,
                y_nm=y,
                z_nm=z,
                E_V_per_m=electric,
                H_A_per_m=magnetic,
            )
            report = compare_selected_planes_to_reference(samples, path)
        self.assertEqual(report["sample_shape_z_y_x_component"], [3, 1, 2, 3])
        self.assertEqual(report["max_middle_plane_electric_relative_l2"], 0.0)
        self.assertEqual(report["max_middle_plane_magnetic_relative_l2"], 0.0)

    def test_full3d_trace_oracle_separates_fit_from_propagation(self) -> None:
        reconstructor = ModalFieldReconstructor.__new__(ModalFieldReconstructor)
        reconstructor.cfg = SimpleNamespace(electric_field_scale_V_per_m=1.0)
        reconstructor.cross_section = SimpleNamespace(
            mesh=SimpleNamespace(comm=MPI.COMM_SELF)
        )
        reconstructor.bottom_z_nm = 10.0
        reconstructor.top_z_nm = 110.0
        reconstructor.positive = SimpleNamespace(
            modes=[SimpleNamespace(beta=0.013 + 0.0j)]
        )
        reconstructor.negative = SimpleNamespace(
            modes=[SimpleNamespace(beta=-0.021 + 0.0j)]
        )
        reconstructor._modes = (
            *reconstructor.positive.modes,
            *reconstructor.negative.modes,
        )
        reconstructor.propagation_model = "full3d_uniform_cg"
        reconstructor._positive_propagation_beta = np.asarray([0.011 + 0.0j])
        reconstructor._negative_propagation_beta = np.asarray([-0.019 + 0.0j])
        electric_basis = np.zeros((2, 2, 3), dtype=np.complex128)
        magnetic_basis = np.zeros((2, 2, 3), dtype=np.complex128)
        electric_basis[0, 0, 0] = 1.0
        electric_basis[0, 1, 1] = 0.25
        electric_basis[1, 0, 1] = 1.0
        electric_basis[1, 1, 0] = -0.5
        magnetic_basis[0, 0, 1] = 2.0
        magnetic_basis[0, 1, 0] = 0.5
        magnetic_basis[1, 0, 0] = -1.5
        magnetic_basis[1, 1, 1] = 0.75
        reconstructor._sample_mode_bases = lambda _points: (
            electric_basis,
            magnetic_basis,
        )
        bottom_coefficients = np.asarray(
            [0.8 - 0.1j, -0.3 + 0.4j],
            dtype=np.complex128,
        )
        beta = np.asarray(
            [mode.beta for mode in reconstructor._modes],
            dtype=np.complex128,
        )
        top_coefficients = bottom_coefficients * np.exp(1j * beta * 100.0)

        def plane(basis, coefficients):
            values = np.einsum("m,mnc->nc", coefficients, basis)
            return values.reshape((1, 2, 3))

        electric = np.stack(
            (
                plane(electric_basis, bottom_coefficients),
                plane(electric_basis, top_coefficients),
            )
        )
        magnetic = np.stack(
            (
                plane(magnetic_basis, bottom_coefficients),
                plane(magnetic_basis, top_coefficients),
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "trace_oracle.npz"
            np.savez_compressed(
                reference,
                x_nm=np.asarray([0.25, 0.75]),
                y_nm=np.asarray([0.5]),
                z_nm=np.asarray([10.0, 110.0]),
                E_V_per_m=electric,
                H_A_per_m=magnetic,
            )
            report = reconstructor.full3d_trace_modal_oracle(reference)
        self.assertEqual(report["interfaces"]["bottom"]["joint_fit_rank"], 2)
        self.assertLess(
            report["interfaces"]["top"]["electric_tangential"]["relative_l2"],
            1.0e-12,
        )
        propagation = report["continuous_propagation"]
        self.assertLess(
            propagation["forward_bottom_to_top"]["coefficient_relative_l2"],
            1.0e-12,
        )
        self.assertLess(
            propagation["backward_top_to_bottom"]["coefficient_relative_l2"],
            1.0e-12,
        )
        self.assertLess(
            propagation["stable_two_sided_reconstruction"]["top_magnetic_tangential"][
                "relative_l2"
            ],
            1.0e-12,
        )
        self.assertEqual(
            report["selected_propagation_model"],
            "full3d_uniform_cg",
        )
        self.assertGreater(
            report["selected_propagation"]["forward_bottom_to_top"][
                "coefficient_relative_l2"
            ],
            1.0e-3,
        )


if __name__ == "__main__":
    unittest.main()
