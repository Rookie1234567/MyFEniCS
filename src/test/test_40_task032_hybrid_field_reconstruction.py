from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import numpy as np

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


if __name__ == "__main__":
    unittest.main()
