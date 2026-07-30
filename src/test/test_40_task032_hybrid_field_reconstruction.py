from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import numpy as np
from mpi4py import MPI

from src.modes.stable_propagation import build_two_sided_propagation
from src.postprocessing.hybrid_field_reconstruction import (
    ModalFieldReconstructor,
    ModalPlaneSamples,
    compare_selected_planes_to_reference,
    relative_sample_error,
)


class TestTask032HybridFieldReconstruction(unittest.TestCase):
    def test_relative_sample_error_is_scale_symmetric(self) -> None:
        first = np.asarray([[1.0 + 1.0j, 2.0], [0.5j, -3.0]], dtype=np.complex128)
        second = 1.01 * first
        forward = relative_sample_error(first, second)
        backward = relative_sample_error(second, first)
        self.assertAlmostEqual(forward["relative_l2"], backward["relative_l2"], places=15)
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

    def test_cg_volume_polynomial_does_not_change_selected_plane_proxy(
        self,
    ) -> None:
        positive_mode = SimpleNamespace(
            beta=0.324456 + 0.002j,
            direction="forward",
            passive_branch_valid=True,
        )
        negative_mode = SimpleNamespace(
            beta=-0.324456 - 0.002j,
            direction="backward",
            passive_branch_valid=True,
        )
        propagation = build_two_sided_propagation(
            [positive_mode, negative_mode],
            10.0,
            propagation_model="full3d_uniform_cg",
            axial_fem_degree=2,
            axial_h_nm=5.0,
        )
        reconstructor = ModalFieldReconstructor.__new__(
            ModalFieldReconstructor
        )
        reconstructor.positive = SimpleNamespace(modes=[positive_mode])
        reconstructor.negative = SimpleNamespace(modes=[negative_mode])
        reconstructor.bottom_z_nm = 10.0
        reconstructor.top_z_nm = 20.0
        reconstructor.propagation_model = "full3d_uniform_cg"
        reconstructor._positive_propagation_beta = np.asarray(
            propagation.forward.effective_beta_per_nm
        )
        reconstructor._negative_propagation_beta = np.asarray(
            propagation.backward.effective_beta_per_nm
        )
        reconstructor._axial_propagation = propagation
        amplitudes = np.asarray(
            [1.0 + 0.25j, -0.4 + 0.1j],
            dtype=np.complex128,
        )
        selected_before = reconstructor.coefficients_at_z(
            amplitudes,
            12.5,
        )
        volume_coefficients = (
            reconstructor._full3d_uniform_cg_coefficients_in_cell(
                amplitudes,
                0,
                0.5,
            )
        )
        selected_after = reconstructor.coefficients_at_z(
            amplitudes,
            12.5,
        )

        np.testing.assert_array_equal(selected_after, selected_before)
        self.assertGreater(
            float(np.linalg.norm(volume_coefficients - selected_before)),
            1.0e-4,
        )
        self.assertEqual(reconstructor._middle_volume_gauss_order(2), 3)
        reconstructor._axial_propagation = build_two_sided_propagation(
            [positive_mode, negative_mode],
            10.0,
            propagation_model="full3d_uniform_cg",
            axial_fem_degree=5,
            axial_h_nm=10.0,
        )
        self.assertEqual(reconstructor._middle_volume_gauss_order(4), 6)

    def test_selected_plane_reference_comparison_round_trip(self) -> None:
        x = np.asarray([0.25, 0.75])
        y = np.asarray([0.5])
        z = np.asarray([10.0, 30.0, 110.0])
        electric = np.arange(18, dtype=np.float64).reshape((3, 1, 2, 3)).astype(np.complex128)
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
        reconstructor.cfg = SimpleNamespace(
            electric_field_scale_V_per_m=1.0
        )
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
        reconstructor._positive_propagation_beta = np.asarray(
            [0.011 + 0.0j]
        )
        reconstructor._negative_propagation_beta = np.asarray(
            [-0.019 + 0.0j]
        )
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
            propagation["forward_bottom_to_top"][
                "coefficient_relative_l2"
            ],
            1.0e-12,
        )
        self.assertLess(
            propagation["backward_top_to_bottom"][
                "coefficient_relative_l2"
            ],
            1.0e-12,
        )
        self.assertLess(
            propagation["stable_two_sided_reconstruction"][
                "top_magnetic_tangential"
            ]["relative_l2"],
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
